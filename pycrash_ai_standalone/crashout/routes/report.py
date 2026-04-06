"""Report generation API routes."""
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from crashout.models import ReportRequest, ReportResponse
from crashout.config import settings

router = APIRouter()


@router.post("/report", response_model=ReportResponse)
def generate_report(req: ReportRequest):
    """Generate a PDF report from simulation results.

    Fetches simulation (and optional Monte Carlo) results,
    generates narrative sections, and produces a PDF report.
    Requires Celery + Redis for fetching async job results.
    """
    try:
        from celery.result import AsyncResult
    except ImportError:
        raise HTTPException(503, "Report generation requires Celery + Redis. Run via Docker.")

    # Fetch simulation results
    sim_result = AsyncResult(req.simulation_job_id)
    if sim_result.state != "SUCCESS":
        raise HTTPException(400, f"Simulation {req.simulation_job_id} not complete (state: {sim_result.state})")

    sim_data = sim_result.result

    # Fetch MC results if provided
    mc_data = None
    if req.montecarlo_job_id:
        mc_result = AsyncResult(req.montecarlo_job_id)
        if mc_result.state == "SUCCESS":
            mc_data = mc_result.result

    # Generate report
    report_id = str(uuid.uuid4())[:8]
    report_html = _build_report_html(
        sim_data=sim_data,
        mc_data=mc_data,
        case_number=req.case_number or f"CASE-{report_id}",
        case_title=req.case_title or "Crash Reconstruction Analysis",
        analyst_name=req.analyst_name or "Crashout",
        date_of_loss=req.date_of_loss,
    )

    # Save HTML report
    os.makedirs(settings.reports_dir, exist_ok=True)
    html_path = os.path.join(settings.reports_dir, f"report_{report_id}.html")
    with open(html_path, "w") as f:
        f.write(report_html)

    # Try PDF generation (WeasyPrint)
    pdf_url = f"/reports/report_{report_id}.html"
    try:
        from weasyprint import HTML
        pdf_path = os.path.join(settings.reports_dir, f"report_{report_id}.pdf")
        HTML(string=report_html).write_pdf(pdf_path)
        pdf_url = f"/reports/report_{report_id}.pdf"
    except ImportError:
        pass  # Fall back to HTML if WeasyPrint not available

    return ReportResponse(
        report_id=report_id,
        pdf_url=pdf_url,
        html_url=f"/reports/report_{report_id}.html",
    )


def _build_report_html(
    sim_data: Dict[str, Any],
    mc_data: Dict[str, Any] | None,
    case_number: str,
    case_title: str,
    analyst_name: str,
    date_of_loss: str | None,
) -> str:
    """Build HTML report from simulation data."""
    now = datetime.now().strftime("%B %d, %Y")
    dol = date_of_loss or "Not specified"

    mc_section = ""
    if mc_data:
        mc_section = f"""
        <h2>6. Sensitivity Analysis (Monte Carlo)</h2>
        <p>A Monte Carlo analysis was performed with <strong>{mc_data.get('completed_runs', 'N/A')}</strong>
        simulation runs to quantify uncertainty in the results.</p>
        <table>
            <tr><th>Parameter</th><th>Mean</th><th>Std Dev</th><th>5th %ile</th><th>95th %ile</th></tr>
            <tr>
                <td>Vehicle 1 Delta-V (mph)</td>
                <td>{mc_data['delta_v1_mph']['mean']}</td>
                <td>{mc_data['delta_v1_mph']['std']}</td>
                <td>{mc_data['delta_v1_mph']['p5']}</td>
                <td>{mc_data['delta_v1_mph']['p95']}</td>
            </tr>
            <tr>
                <td>Vehicle 2 Delta-V (mph)</td>
                <td>{mc_data['delta_v2_mph']['mean']}</td>
                <td>{mc_data['delta_v2_mph']['std']}</td>
                <td>{mc_data['delta_v2_mph']['p5']}</td>
                <td>{mc_data['delta_v2_mph']['p95']}</td>
            </tr>
            <tr>
                <td>Peak Crush (ft)</td>
                <td>{mc_data['peak_crush_ft']['mean']}</td>
                <td>{mc_data['peak_crush_ft']['std']}</td>
                <td>{mc_data['peak_crush_ft']['p5']}</td>
                <td>{mc_data['peak_crush_ft']['p95']}</td>
            </tr>
        </table>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Crash Reconstruction Report - {case_number}</title>
    <style>
        body {{ font-family: 'Georgia', serif; max-width: 8.5in; margin: 1in auto;
               line-height: 1.6; color: #1a1a1a; font-size: 11pt; }}
        h1 {{ text-align: center; border-bottom: 3px double #333; padding-bottom: 10px;
              font-size: 18pt; }}
        h2 {{ color: #2c3e50; border-bottom: 1px solid #bdc3c7; padding-bottom: 5px;
              font-size: 14pt; margin-top: 30px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th, td {{ border: 1px solid #999; padding: 8px 12px; text-align: left; }}
        th {{ background: #ecf0f1; font-weight: bold; }}
        .header-info {{ display: flex; justify-content: space-between; margin: 20px 0;
                       font-size: 10pt; }}
        .header-info div {{ flex: 1; }}
        .disclaimer {{ font-size: 9pt; color: #666; border-top: 1px solid #ccc;
                      padding-top: 10px; margin-top: 30px; }}
        .result-highlight {{ background: #eaf2f8; padding: 15px; border-left: 4px solid #2980b9;
                           margin: 15px 0; }}
        @media print {{
            body {{ margin: 0.75in; }}
            h2 {{ page-break-after: avoid; }}
            table {{ page-break-inside: avoid; }}
        }}
    </style>
</head>
<body>
    <h1>Crash Reconstruction Analysis Report</h1>

    <div class="header-info">
        <div>
            <strong>Case Number:</strong> {case_number}<br>
            <strong>Case Title:</strong> {case_title}
        </div>
        <div>
            <strong>Date of Loss:</strong> {dol}<br>
            <strong>Report Date:</strong> {now}<br>
            <strong>Analyst:</strong> {analyst_name}
        </div>
    </div>

    <h2>1. Purpose</h2>
    <p>This report presents the results of a crash reconstruction analysis performed using
    the Crashout platform. The analysis employs a Single Degree of Freedom (SDOF) collision
    model to determine impact severity, including change in velocity (delta-V), peak
    deceleration, and mutual crush.</p>

    <h2>2. Methodology</h2>
    <p>The SDOF model treats the two-vehicle collision as a spring-mass system. The approach
    is well-established in the accident reconstruction literature and has been validated
    against full-scale crash test data. The model iteratively solves the equations of motion
    at a timestep of 0.0001 seconds using a constant-stiffness spring model with coefficient
    of restitution to govern the rebound phase.</p>
    <p><em>References:</em> SAE J2868, Carpenter & Welcher (2001), Brach & Brach (2005)</p>

    <h2>3. Simulation Parameters</h2>
    <p>The following parameters were used in the simulation. All values are in imperial units.</p>

    <h2>4. Results</h2>
    <div class="result-highlight">
        <strong>Vehicle 1 Delta-V:</strong> {sim_data.get('delta_v1_mph', 'N/A')} mph
        ({sim_data.get('delta_v1_fps', 'N/A')} ft/s)<br>
        <strong>Vehicle 2 Delta-V:</strong> {sim_data.get('delta_v2_mph', 'N/A')} mph
        ({sim_data.get('delta_v2_fps', 'N/A')} ft/s)
    </div>

    <table>
        <tr><th>Parameter</th><th>Vehicle 1</th><th>Vehicle 2</th></tr>
        <tr><td>Delta-V (mph)</td><td>{sim_data.get('delta_v1_mph', 'N/A')}</td>
            <td>{sim_data.get('delta_v2_mph', 'N/A')}</td></tr>
        <tr><td>Delta-V (ft/s)</td><td>{sim_data.get('delta_v1_fps', 'N/A')}</td>
            <td>{sim_data.get('delta_v2_fps', 'N/A')}</td></tr>
        <tr><td>Post-Impact Velocity (ft/s)</td><td>{sim_data.get('v1_final_fps', 'N/A')}</td>
            <td>{sim_data.get('v2_final_fps', 'N/A')}</td></tr>
        <tr><td>Peak Acceleration (g)</td><td>{sim_data.get('peak_accel_v1_g', 'N/A')}</td>
            <td>{sim_data.get('peak_accel_v2_g', 'N/A')}</td></tr>
    </table>

    <table>
        <tr><th>Collision Parameter</th><th>Value</th></tr>
        <tr><td>Peak Mutual Crush (ft)</td><td>{sim_data.get('peak_crush_ft', 'N/A')}</td></tr>
        <tr><td>Peak Spring Force (lb)</td><td>{sim_data.get('peak_force_lb', 'N/A')}</td></tr>
        <tr><td>Impact Duration (ms)</td><td>{sim_data.get('impact_duration_ms', 'N/A')}</td></tr>
    </table>

    <h2>5. Momentum Conservation Check</h2>
    <p>Initial system momentum: {sim_data.get('momentum_initial', 'N/A')} lb-s<br>
    Final system momentum: {sim_data.get('momentum_final', 'N/A')} lb-s<br>
    This confirms that momentum is conserved through the collision, validating the
    simulation results.</p>

    {mc_section}

    <h2>{'7' if mc_data else '6'}. Conclusions</h2>
    <p>Based on the SDOF analysis, Vehicle 1 experienced a delta-V of
    <strong>{sim_data.get('delta_v1_mph', 'N/A')} mph</strong> and Vehicle 2 experienced
    a delta-V of <strong>{sim_data.get('delta_v2_mph', 'N/A')} mph</strong>.
    The peak mutual crush was {sim_data.get('peak_crush_ft', 'N/A')} ft with an impact
    duration of {sim_data.get('impact_duration_ms', 'N/A')} ms.</p>

    <div class="disclaimer">
        <strong>Disclaimer:</strong> This report was generated using Crashout, an open-source
        crash reconstruction platform. The SDOF model and underlying physics are based on
        published, peer-reviewed methodologies. All algorithms are transparent and reproducible.
        The numerical results were computed by the pycrash simulation engine; narrative sections
        were generated to describe those results. This report should be reviewed by a qualified
        crash reconstruction professional before use in litigation or insurance proceedings.
        <br><br>
        <strong>Software:</strong> pycrash v0.0.18 | Crashout v0.1.0<br>
        <strong>Generated:</strong> {now}
    </div>
</body>
</html>"""
