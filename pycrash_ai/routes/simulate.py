"""Simulation API routes."""
from __future__ import annotations

import math

from fastapi import APIRouter, HTTPException

from pycrash_ai.models import SDOFRequest, SimulationStatus, IMPCRequest, SideswipeRequest, VisualizationRequest

router = APIRouter()


@router.post("/simulate/sdof", response_model=SimulationStatus)
def start_sdof_simulation(req: SDOFRequest):
    """Queue an SDOF crash simulation (requires Celery + Redis)."""
    try:
        from pycrash_ai.tasks.simulation_tasks import run_sdof_simulation
        task = run_sdof_simulation.delay(req.model_dump())
        return SimulationStatus(job_id=task.id, status="queued")
    except ImportError:
        raise HTTPException(503, "Async simulation requires Celery + Redis. Use /simulate/sdof/sync instead or run via Docker.")


@router.post("/simulate/sdof/sync")
def run_sdof_sync(req: SDOFRequest):
    """Run SDOF simulation synchronously (no Redis/Celery needed)."""
    from pycrash.sdof_calcs.sdof_calculations import SingleDOFmodel

    result_df = SingleDOFmodel(
        W1=req.w1, v1_initial=req.v1, v1_brake=req.v1_brake,
        W2=req.w2, v2_initial=req.v2, v2_brake=req.v2_brake,
        k=req.k, cor=req.cor, tstop=req.tstop,
        ktype="constantK", ttype=1,
    )

    m1, m2 = req.w1 / 32.2, req.w2 / 32.2
    v1_init = req.v1 * 1.46667
    v2_init = req.v2 * 1.46667
    v1_final = float(result_df.v1.iloc[-1])
    v2_final = float(result_df.v2.iloc[-1])

    return {
        "status": "complete",
        "delta_v1_mph": round(abs(v1_final - v1_init) * 0.681818, 2),
        "delta_v2_mph": round(abs(v2_final - v2_init) * 0.681818, 2),
        "peak_crush_ft": round(abs(float(result_df.dx.min())), 4),
        "peak_force_lb": round(float(result_df.springF.max()), 1),
        "peak_accel_v1_g": round(float(result_df.a1.abs().max()) / 32.2, 2),
        "peak_accel_v2_g": round(float(result_df.a2.abs().max()) / 32.2, 2),
        "v1_final_fps": round(v1_final, 2),
        "v2_final_fps": round(v2_final, 2),
        "momentum_conserved": round(
            abs((m1 * v1_final + m2 * v2_final) - (m1 * v1_init + m2 * v2_init)), 4
        ),
    }


@router.post("/simulate/impc/sync")
def run_impc_sync(req: IMPCRequest):
    """Run impulse-momentum planar collision synchronously.

    This is a simplified standalone IMPC calculation based on the
    Carpenter & Welcher momentum model. It computes instantaneous
    collision impulse and resulting delta-V for two vehicles given
    pre-impact speeds, heading angles, and impact geometry.

    Limitations vs. the full pycrash Impact simulation:
    - No pre/post-impact trajectory integration or tire model
    - No automatic impact point detection (offsets from CG are user-specified)
    - Single collision only (no multi-impact sequences)
    - No sideswipe or continuous-contact phase
    """
    v1 = req.vehicle1
    v2 = req.vehicle2
    cor = req.cor
    cof = req.vehicle_mu

    # Convert speeds to ft/s
    vx1 = v1.speed_mph * 1.46667
    vy1 = v1.lateral_speed_mph * 1.46667
    vx2 = v2.speed_mph * 1.46667
    vy2 = v2.lateral_speed_mph * 1.46667

    # Heading angles in radians
    theta1 = math.radians(v1.heading_deg)
    theta2 = math.radians(v2.heading_deg)

    # Yaw rates in rad/s
    oz1 = math.radians(v1.yaw_rate_deg_s)
    oz2 = math.radians(v2.yaw_rate_deg_s)

    # Masses
    m1 = v1.weight / 32.2
    m2 = v2.weight / 32.2

    # Impact point offsets from CG (vehicle frame)
    dx1 = v1.impact_dx_ft
    dy1 = v1.impact_dy_ft
    dx2 = v2.impact_dx_ft
    dy2 = v2.impact_dy_ft

    # Impact plane angle: theta_c is the tangent direction in global frame
    theta_c = theta1 + math.radians(req.impact_plane_angle_deg) + math.pi / 2

    # Coordinate transform angles
    c1 = math.cos(theta1 - theta_c)
    s1 = math.sin(theta1 - theta_c)
    c2 = math.cos(theta2 - theta_c)
    s2 = math.sin(theta2 - theta_c)

    # Translate distances to n-t frame
    dt1 = c1 * dx1 - s1 * dy1
    dn1 = s1 * dx1 + c1 * dy1
    dt2 = c2 * dx2 - s2 * dy2
    dn2 = s2 * dx2 + c2 * dy2

    # Translate velocities to n-t frame
    vt1 = c1 * vx1 - s1 * vy1
    vn1 = s1 * vx1 + c1 * vy1
    vt2 = c2 * vx2 - s2 * vy2
    vn2 = s2 * vx2 + c2 * vy2

    # Pre-impact POI velocities (Carpenter Eq. 1)
    vct21 = (vt2 - dn2 * oz2) - (vt1 - dn1 * oz1)
    vcn21 = (vn2 + dt2 * oz2) - (vn1 + dt1 * oz1)

    # A-matrix terms
    A11 = 1 / m1 + 1 / m2 + dn1**2 / v1.izz + dn2**2 / v2.izz
    A12 = dt1 * dn1 / v1.izz + dt2 * dn2 / v2.izz
    A22 = 1 / m1 + 1 / m2 + dt1**2 / v1.izz + dt2**2 / v2.izz
    A_det = A11 * A22 - A12 * A12

    if abs(A_det) < 1e-12:
        raise HTTPException(400, "Degenerate impact geometry (A-matrix singular). Check impact point offsets and moments of inertia.")

    # Collision impulse
    pt = (1 + cor) * (A22 * vct21 + A12 * vcn21) / A_det
    pn = (1 + cor) * (A12 * vct21 + A11 * vcn21) / A_det

    # Check sliding condition
    sliding = False
    if abs(pn) > 1e-10 and abs(pt / pn) > cof:
        sliding = True
        alpha = 1
        pn_s = (1 + cor) * vcn21 / (A22 - cof * A12)
        pt_s = alpha * cof * pn_s
        if pt * pt_s > 0:
            pt = pt_s
            pn = pn_s
        else:
            alpha = -1
            pn = (1 + cor) * vcn21 / (A22 + cof * A12)
            pt = alpha * cof * pn

    # Delta-V in collision frame
    dvt1 = pt / m1
    dvn1 = pn / m1
    doz1 = (-dn1 * pt + dt1 * pn) / v1.izz

    dvt2 = -pt / m2
    dvn2 = -pn / m2
    doz2 = (dn2 * pt - dt2 * pn) / v2.izz

    # Transform back to vehicle local frame
    dvx1 = c1 * dvt1 + s1 * dvn1
    dvy1 = -s1 * dvt1 + c1 * dvn1
    dv1_mag = math.sqrt(dvx1**2 + dvy1**2)

    dvx2 = c2 * dvt2 + s2 * dvn2
    dvy2 = -s2 * dvt2 + c2 * dvn2
    dv2_mag = math.sqrt(dvx2**2 + dvy2**2)

    # Post-impact velocities (vehicle frame)
    vx1_post = vx1 + dvx1
    vy1_post = vy1 + dvy1
    vx2_post = vx2 + dvx2
    vy2_post = vy2 + dvy2

    # PDOF (principal direction of force) relative to vehicle heading
    pdof1_rad = math.atan2(dvy1, dvx1) if abs(dv1_mag) > 1e-10 else 0.0
    pdof2_rad = math.atan2(dvy2, dvx2) if abs(dv2_mag) > 1e-10 else 0.0

    # Energy dissipated
    if cor < 1:
        vmt1 = vt1 + dvt1 / (1 + cor)
        vmt2 = vt2 + dvt2 / (1 + cor)
        omgm1 = oz1 + doz1 / (1 + cor)
        omgm2 = oz2 + doz2 / (1 + cor)
    else:
        vmt1 = vt1
        vmt2 = vt2
        omgm1 = oz1
        omgm2 = oz2
    vmct21 = vmt2 - vmt1 - dn2 * omgm2 + dn1 * omgm1

    ke_surface_dis = pt * vmct21
    ke_volume_dis = 0.5 * (1 - cor) * (pt * (vct21 - vmct21) + pn * vcn21)
    ke_total_dis = ke_surface_dis + ke_volume_dis

    fps_to_mph = 0.681818

    return {
        "status": "complete",
        "model": "impc",
        "sliding": sliding,
        "vehicle1": {
            "delta_v_mph": round(dv1_mag * fps_to_mph, 2),
            "delta_vx_mph": round(dvx1 * fps_to_mph, 2),
            "delta_vy_mph": round(dvy1 * fps_to_mph, 2),
            "post_vx_mph": round(vx1_post * fps_to_mph, 2),
            "post_vy_mph": round(vy1_post * fps_to_mph, 2),
            "post_speed_mph": round(math.sqrt(vx1_post**2 + vy1_post**2) * fps_to_mph, 2),
            "delta_yaw_rate_deg_s": round(math.degrees(doz1), 2),
            "pdof_deg": round(math.degrees(pdof1_rad), 1),
        },
        "vehicle2": {
            "delta_v_mph": round(dv2_mag * fps_to_mph, 2),
            "delta_vx_mph": round(dvx2 * fps_to_mph, 2),
            "delta_vy_mph": round(dvy2 * fps_to_mph, 2),
            "post_vx_mph": round(vx2_post * fps_to_mph, 2),
            "post_vy_mph": round(vy2_post * fps_to_mph, 2),
            "post_speed_mph": round(math.sqrt(vx2_post**2 + vy2_post**2) * fps_to_mph, 2),
            "delta_yaw_rate_deg_s": round(math.degrees(doz2), 2),
            "pdof_deg": round(math.degrees(pdof2_rad), 1),
        },
        "energy": {
            "surface_dissipated_ft_lb": round(ke_surface_dis, 1),
            "volume_dissipated_ft_lb": round(ke_volume_dis, 1),
            "total_dissipated_ft_lb": round(ke_total_dis, 1),
        },
        "impulse": {
            "tangential_lb_s": round(pt, 2),
            "normal_lb_s": round(pn, 2),
        },
    }


@router.post("/simulate/sideswipe/sync")
def run_sideswipe_sync(req: SideswipeRequest):
    """Run simplified sideswipe collision synchronously.

    This is a simplified sideswipe model that calculates forces and
    velocity changes from continuous lateral contact between two vehicles.
    It uses the crush depth * mutual stiffness approach for normal force
    and friction coefficient for tangential force.

    Limitations vs. the full pycrash sideswipe model:
    - No timestep-by-timestep integration with tire forces
    - No vehicle dynamics or trajectory simulation during contact
    - Simplified impulse calculation from average force * contact time
    - Assumes constant overlap depth throughout contact
    - No edge-specific geometry (front/side/rear)
    """
    v1 = req.vehicle1
    v2 = req.vehicle2

    # Convert speeds to ft/s
    v1_fwd = v1.speed_mph * 1.46667
    v1_lat = v1.lateral_speed_mph * 1.46667
    v2_fwd = v2.speed_mph * 1.46667
    v2_lat = v2.lateral_speed_mph * 1.46667

    # Masses
    m1 = v1.weight / 32.2
    m2 = v2.weight / 32.2

    # Normal force from crush
    f_normal = req.overlap_ft * req.kmutual  # lb

    # Heading angles in radians
    heading1_rad = math.radians(v1.heading_deg)
    heading2_rad = math.radians(v2.heading_deg)

    # Global velocities
    Vx1 = v1_fwd * math.cos(heading1_rad) - v1_lat * math.sin(heading1_rad)
    Vy1 = v1_fwd * math.sin(heading1_rad) + v1_lat * math.cos(heading1_rad)
    Vx2 = v2_fwd * math.cos(heading2_rad) - v2_lat * math.sin(heading2_rad)
    Vy2 = v2_fwd * math.sin(heading2_rad) + v2_lat * math.cos(heading2_rad)

    # Average contact direction
    avg_heading = (heading1_rad + heading2_rad) / 2
    rel_vx = Vx1 - Vx2
    rel_vy = Vy1 - Vy2

    # Project relative velocity along and normal to average contact direction
    rel_tangential = rel_vx * math.cos(avg_heading) + rel_vy * math.sin(avg_heading)

    # Friction force opposes relative tangential motion
    f_friction = req.vehicle_mu * f_normal  # magnitude
    if rel_tangential != 0:
        f_friction *= -1 * (rel_tangential / abs(rel_tangential))  # direction

    # Contact duration estimate: time for vehicles to traverse contact length
    rel_speed = abs(rel_tangential) if abs(rel_tangential) > 0.1 else abs(v1_fwd - v2_fwd)
    if rel_speed > 0.1:
        contact_time = req.contact_length_ft / rel_speed
    else:
        contact_time = 0.1  # small default for near-zero relative speed
    contact_time = min(contact_time, 2.0)

    # Impulse = force * time
    impulse_normal = f_normal * contact_time
    impulse_friction = f_friction * contact_time

    # Velocity changes (applied along average contact direction)
    dv1_normal = impulse_normal / m1
    dv2_normal = -impulse_normal / m2

    dv1_friction = impulse_friction / m1
    dv2_friction = -impulse_friction / m2

    # Convert to global frame
    sin_h = math.sin(avg_heading)
    cos_h = math.cos(avg_heading)

    dVx1 = -sin_h * dv1_normal + cos_h * dv1_friction
    dVy1 = cos_h * dv1_normal + sin_h * dv1_friction
    dVx2 = -sin_h * dv2_normal + cos_h * dv2_friction
    dVy2 = cos_h * dv2_normal + sin_h * dv2_friction

    # Post-impact global velocities
    Vx1_post = Vx1 + dVx1
    Vy1_post = Vy1 + dVy1
    Vx2_post = Vx2 + dVx2
    Vy2_post = Vy2 + dVy2

    dv1_total = math.sqrt(dVx1**2 + dVy1**2)
    dv2_total = math.sqrt(dVx2**2 + dVy2**2)

    # Energy dissipated
    ke_crush = 0.5 * req.kmutual * req.overlap_ft**2 * req.contact_length_ft
    ke_friction = abs(f_friction * rel_tangential * contact_time) if abs(rel_tangential) > 0.01 else 0.0

    fps_to_mph = 0.681818

    return {
        "status": "complete",
        "model": "sideswipe",
        "contact_time_s": round(contact_time, 4),
        "normal_force_lb": round(f_normal, 1),
        "friction_force_lb": round(abs(f_friction), 1),
        "vehicle1": {
            "delta_v_mph": round(dv1_total * fps_to_mph, 2),
            "post_speed_mph": round(math.sqrt(Vx1_post**2 + Vy1_post**2) * fps_to_mph, 2),
            "post_Vx_mph": round(Vx1_post * fps_to_mph, 2),
            "post_Vy_mph": round(Vy1_post * fps_to_mph, 2),
        },
        "vehicle2": {
            "delta_v_mph": round(dv2_total * fps_to_mph, 2),
            "post_speed_mph": round(math.sqrt(Vx2_post**2 + Vy2_post**2) * fps_to_mph, 2),
            "post_Vx_mph": round(Vx2_post * fps_to_mph, 2),
            "post_Vy_mph": round(Vy2_post * fps_to_mph, 2),
        },
        "energy": {
            "crush_energy_ft_lb": round(ke_crush, 1),
            "friction_energy_ft_lb": round(ke_friction, 1),
            "total_dissipated_ft_lb": round(ke_crush + ke_friction, 1),
        },
        "impulse": {
            "normal_lb_s": round(impulse_normal, 2),
            "friction_lb_s": round(abs(impulse_friction), 2),
        },
    }


@router.get("/simulate/{job_id}", response_model=SimulationStatus)
def get_simulation_status(job_id: str):
    """Check simulation job status (requires Celery + Redis)."""
    try:
        from celery.result import AsyncResult
    except ImportError:
        raise HTTPException(503, "Job status requires Celery. Run via Docker.")

    result = AsyncResult(job_id)

    if result.state == "PENDING":
        return SimulationStatus(job_id=job_id, status="queued")
    elif result.state == "RUNNING":
        meta = result.info or {}
        return SimulationStatus(
            job_id=job_id, status="running",
            progress=meta.get("progress", 0),
        )
    elif result.state == "SUCCESS":
        return SimulationStatus(
            job_id=job_id, status="complete",
            progress=1.0, results=result.result,
        )
    elif result.state == "FAILURE":
        return SimulationStatus(
            job_id=job_id, status="failed",
            error=str(result.info),
        )
    else:
        return SimulationStatus(job_id=job_id, status=result.state)


def _vehicle_corners(x: float, y: float, length: float, width: float, heading_deg: float) -> list[tuple[float, float]]:
    """Compute the four corners of a rotated vehicle rectangle."""
    h = math.radians(heading_deg)
    cos_h, sin_h = math.cos(h), math.sin(h)
    hw, hl = width / 2, length / 2
    corners = [
        (x + hl * cos_h - hw * sin_h, y + hl * sin_h + hw * cos_h),  # front-left
        (x + hl * cos_h + hw * sin_h, y + hl * sin_h - hw * cos_h),  # front-right
        (x - hl * cos_h + hw * sin_h, y - hl * sin_h - hw * cos_h),  # rear-right
        (x - hl * cos_h - hw * sin_h, y - hl * sin_h + hw * cos_h),  # rear-left
    ]
    return corners


@router.post("/simulate/visualize")
def generate_crash_visualization(req: VisualizationRequest):
    """Generate a 2D crash scene diagram as Plotly JSON."""
    traces = []

    for veh in req.vehicles:
        corners = _vehicle_corners(veh.x, veh.y, veh.length, veh.width, veh.heading)
        # Close the polygon by repeating the first corner
        xs = [c[0] for c in corners] + [corners[0][0]]
        ys = [c[1] for c in corners] + [corners[0][1]]

        # Filled vehicle polygon
        traces.append({
            "type": "scatter",
            "x": xs,
            "y": ys,
            "mode": "lines",
            "fill": "toself",
            "fillcolor": veh.color,
            "opacity": 0.4,
            "line": {"color": veh.color, "width": 2},
            "name": veh.label,
            "showlegend": True,
        })

        # Vehicle label at center
        traces.append({
            "type": "scatter",
            "x": [veh.x],
            "y": [veh.y],
            "mode": "text",
            "text": [veh.label],
            "textposition": "middle center",
            "textfont": {"size": 11, "color": "black"},
            "showlegend": False,
        })

    # Impact point marker
    if req.impact_point and "x" in req.impact_point and "y" in req.impact_point:
        traces.append({
            "type": "scatter",
            "x": [req.impact_point["x"]],
            "y": [req.impact_point["y"]],
            "mode": "markers+text",
            "marker": {"symbol": "x", "size": 14, "color": "red", "line": {"width": 2}},
            "text": ["Impact"],
            "textposition": "top center",
            "textfont": {"size": 10, "color": "red"},
            "name": "Impact Point",
            "showlegend": True,
        })

    layout = {
        "title": {"text": req.title},
        "xaxis": {
            "title": "X (ft)",
            "scaleanchor": "y",
            "scaleratio": 1,
            "showgrid": req.show_grid,
            "gridcolor": "#e5e7eb",
            "zeroline": True,
        },
        "yaxis": {
            "title": "Y (ft)",
            "showgrid": req.show_grid,
            "gridcolor": "#e5e7eb",
            "zeroline": True,
        },
        "showlegend": True,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Inter, system-ui, sans-serif", "size": 12},
        "margin": {"t": 50, "r": 20, "b": 50, "l": 60},
    }

    fig_dict = {"data": traces, "layout": layout}
    return {"plotly_json": fig_dict}
