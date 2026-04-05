/**
 * CrashAnimation - 2D top-down animated crash simulation on HTML5 canvas.
 *
 * Renders two vehicles approaching, colliding with impact effects, separating,
 * and displaying final results. Driven by SDOF simulation output data.
 *
 * Usage:
 *   const anim = new CrashAnimation(document.getElementById('crash-canvas'));
 *   anim.animate(results, params);
 */
class CrashAnimation {
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.width = canvas.width || 800;
    this.height = canvas.height || 400;

    this.duration = options.duration || 3000;
    this.colors = {
      v1: options.v1Color || '#3b82f6',
      v2: options.v2Color || '#ef4444',
      road: '#374151',
      lane: '#fbbf24',
      grass: '#86efac',
      impact: '#f97316',
      spark: '#fbbf24',
    };

    this.animating = false;
    this.frameId = null;
    this.startTime = null;
    this.results = null;
    this.params = null;
    this.sparks = [];
    this.shakeX = 0;
    this.shakeY = 0;
    this.onComplete = options.onComplete || null;

    // Vehicle pixel dimensions
    this.carW = 36;
    this.carH = 70;

    // Replay click handler (attached once)
    this._replayBounds = null;
    this._replayListenerAttached = false;
  }

  // ---------------------------------------------------------------- public API

  /**
   * Start the crash animation with SDOF results and input parameters.
   *
   * @param {Object} results - SDOF simulation output
   * @param {Object} params  - Input parameters (weights, speeds, braking)
   */
  animate(results, params) {
    this.stop();
    this.results = results;
    this.params = params;

    // Pre-compute speeds
    this.v1_initial_fps = params.v1 * 1.46667;
    this.v2_initial_fps = params.v2 * 1.46667;
    this.v1_final_fps = results.v1_final_fps;
    this.v2_final_fps = results.v2_final_fps;
    this.v1_init_mph = params.v1;
    this.v2_init_mph = params.v2;
    this.dv1 = results.delta_v1_mph;
    this.dv2 = results.delta_v2_mph;
    this.crush = results.peak_crush_ft;
    this.peakForce = results.peak_force_lb;

    // Layout positions
    this.cx = this.width * 0.50;
    this.cy = this.height * 0.48;
    this.v1Start = this.width * 0.10;
    this.v2Start = params.v2 === 0
      ? this.cx + this.carH / 2 + 2
      : this.width * 0.90;
    this.v1Impact = this.cx - this.carH / 2 - 2;
    this.v2Impact = this.cx + this.carH / 2 + 2;

    // Post-impact drift distances scaled to delta-V
    const maxDrift = this.width * 0.20;
    const v1f_mph = Math.abs(this.v1_final_fps * 0.681818);
    const v2f_mph = Math.abs(this.v2_final_fps * 0.681818);
    const topSpeed = Math.max(this.v1_init_mph, 1);
    this.v1End = this.v1Impact - (v1f_mph / topSpeed) * maxDrift * 0.4;
    this.v2End = this.v2Impact + (v2f_mph / topSpeed) * maxDrift;

    // Pre-generate spark particles
    this.sparks = [];
    for (let i = 0; i < 14; i++) {
      const angle = (Math.PI * 2 * i) / 14 + (Math.random() - 0.5) * 0.45;
      this.sparks.push({
        angle,
        speed: 45 + Math.random() * 75,
        size: 2 + Math.random() * 3.5,
        life: 0.55 + Math.random() * 0.45,
        bright: Math.random() > 0.4,
      });
    }

    this.startTime = performance.now();
    this.animating = true;
    this._replayBounds = null;
    this.frameId = requestAnimationFrame((ts) => this._loop(ts));
  }

  /** Stop the animation immediately. */
  stop() {
    this.animating = false;
    if (this.frameId) {
      cancelAnimationFrame(this.frameId);
      this.frameId = null;
    }
  }

  /** Stop and clear the canvas to an idle state. */
  reset() {
    this.stop();
    this.results = null;
    this.params = null;
    this._drawIdle();
  }

  /** Draw a static idle scene (two parked vehicles). */
  drawIdle() {
    this._drawIdle();
  }

  // ---------------------------------------------------------- animation loop

  _loop(timestamp) {
    if (!this.animating) return;
    const elapsed = timestamp - this.startTime;
    const t = Math.min(elapsed / this.duration, 1.0);

    this._drawFrame(t);

    if (t < 1.0) {
      this.frameId = requestAnimationFrame((ts) => this._loop(ts));
    } else {
      this.animating = false;
      this._drawReplayButton();
      if (this.onComplete) this.onComplete();
    }
  }

  // ------------------------------------------------------------- main render

  _drawFrame(t) {
    const ctx = this.ctx;
    ctx.save();
    ctx.imageSmoothingEnabled = true;

    // Screen shake during impact window
    this.shakeX = 0;
    this.shakeY = 0;
    if (t > 0.38 && t < 0.56) {
      const intensity = Math.sin((t - 0.38) / 0.18 * Math.PI) * 5;
      this.shakeX = (Math.random() - 0.5) * intensity;
      this.shakeY = (Math.random() - 0.5) * intensity;
    }
    ctx.translate(this.shakeX, this.shakeY);

    // Draw scene layers
    this._drawRoad();

    // Compute positions & visual state for this frame
    const state = this._computeState(t);

    // Draw vehicles
    this._drawVehicle(
      state.v1x, this.cy - 4, 90,
      this.carW, this.carH, this.colors.v1,
      'Vehicle 1 \u2014 ' + (this.params.w1 || 3400).toLocaleString() + ' lb',
      state.crush1, state.damaged
    );
    this._drawVehicle(
      state.v2x, this.cy + 4, -90,
      this.carW, this.carH, this.colors.v2,
      'Vehicle 2 \u2014 ' + (this.params.w2 || 3000).toLocaleString() + ' lb',
      state.crush2, state.damaged
    );

    // Impact visual effects
    if (t >= 0.37 && t < 0.62) {
      this._drawImpactEffect(this.cx, this.cy, (t - 0.37) / 0.25);
    }

    // "IMPACT" text flash
    if (t >= 0.39 && t < 0.54) {
      const fade = t < 0.43
        ? (t - 0.39) / 0.04
        : 1.0 - (t - 0.43) / 0.11;
      this._drawImpactText(Math.max(0, Math.min(1, fade)));
    }

    // Speedometers
    this._drawSpeedometer(
      64, this.height - 54, state.v1Speed, 'V1', this.colors.v1
    );
    this._drawSpeedometer(
      this.width - 64, this.height - 54, state.v2Speed, 'V2', this.colors.v2
    );

    // Phase indicator
    this._drawInfoPanel(t);

    // Results overlay (phase 4)
    if (t > 0.80) {
      const fadeIn = Math.min((t - 0.80) / 0.12, 1.0);
      this._drawResultsOverlay(state.v1x, state.v2x, fadeIn);
    }

    ctx.restore();
  }

  // -------------------------------------------------------- position compute

  _computeState(t) {
    let v1x, v2x, crush1 = 1, crush2 = 1, damaged = false;
    let v1Speed, v2Speed;

    const v1f_mph = Math.abs(this.v1_final_fps * 0.681818);
    const v2f_mph = Math.abs(this.v2_final_fps * 0.681818);

    if (t <= 0.40) {
      // Phase 1: Approach
      const p = this._easeInOut(t / 0.40);
      v1x = this.v1Start + (this.v1Impact - this.v1Start) * p;
      v2x = this.v2Start + (this.v2Impact - this.v2Start) * p;
      v1Speed = this.v1_init_mph * (1.0 - p * 0.08);
      v2Speed = this.v2_init_mph;
    } else if (t <= 0.50) {
      // Phase 2: Impact / crush
      const p = (t - 0.40) / 0.10;
      v1x = this.v1Impact;
      v2x = this.v2Impact;
      const crushPx = Math.sin(p * Math.PI) * 0.13;
      crush1 = 1.0 - crushPx;
      crush2 = 1.0 - crushPx * 0.85;
      v1Speed = this.v1_init_mph * (1.0 - p);
      v2Speed = v2f_mph * p;
    } else if (t <= 0.80) {
      // Phase 3: Separation
      const p = this._easeOut((t - 0.50) / 0.30);
      v1x = this.v1Impact + (this.v1End - this.v1Impact) * p;
      v2x = this.v2Impact + (this.v2End - this.v2Impact) * p;
      crush1 = 1;
      crush2 = 1;
      damaged = true;
      v1Speed = v1f_mph * (1.0 - p * 0.25);
      v2Speed = v2f_mph * (1.0 - p * 0.25);
    } else {
      // Phase 4: At rest
      v1x = this.v1End;
      v2x = this.v2End;
      damaged = true;
      v1Speed = v1f_mph * 0.75;
      v2Speed = v2f_mph * 0.75;
    }

    return {
      v1x, v2x,
      crush1, crush2,
      damaged,
      v1Speed: Math.abs(v1Speed),
      v2Speed: Math.abs(v2Speed),
    };
  }

  // -------------------------------------------------------------- draw: road

  _drawRoad() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const roadTop = this.cy - 68;
    const roadBot = this.cy + 68;

    // Dark background
    ctx.fillStyle = '#1e293b';
    ctx.fillRect(0, 0, w, h);

    // Grass shoulders
    ctx.fillStyle = this.colors.grass;
    ctx.globalAlpha = 0.18;
    ctx.fillRect(0, roadTop - 16, w, 16);
    ctx.fillRect(0, roadBot, w, 16);
    ctx.globalAlpha = 1.0;

    // Road surface
    ctx.fillStyle = this.colors.road;
    ctx.fillRect(0, roadTop, w, roadBot - roadTop);

    // White edge lines
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(0, roadTop + 1);
    ctx.lineTo(w, roadTop + 1);
    ctx.moveTo(0, roadBot - 1);
    ctx.lineTo(w, roadBot - 1);
    ctx.stroke();

    // Yellow dashed center line
    ctx.strokeStyle = this.colors.lane;
    ctx.lineWidth = 2.5;
    ctx.setLineDash([20, 14]);
    ctx.beginPath();
    ctx.moveTo(0, this.cy);
    ctx.lineTo(w, this.cy);
    ctx.stroke();
    ctx.setLineDash([]);

    // Distance markers along bottom
    ctx.fillStyle = '#64748b';
    ctx.font = '10px system-ui, sans-serif';
    ctx.textAlign = 'center';
    for (let i = 0; i <= 8; i++) {
      const mx = (w / 8) * i;
      ctx.fillText(i * 10 + ' ft', mx, roadBot + 30);
      ctx.fillRect(mx - 0.5, roadBot + 4, 1, 5);
    }
  }

  // ---------------------------------------------------------- draw: vehicle

  _drawVehicle(x, y, headingDeg, vw, vh, color, label, scaleX, damaged) {
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((headingDeg * Math.PI) / 180);

    const hw = vw / 2;
    const hh = (vh * scaleX) / 2;

    // Drop shadow
    ctx.fillStyle = 'rgba(0,0,0,0.22)';
    this._roundRect(ctx, -hw + 3, -hh + 3, vw, vh * scaleX, 6);
    ctx.fill();

    // Main body
    ctx.fillStyle = color;
    this._roundRect(ctx, -hw, -hh, vw, vh * scaleX, 6);
    ctx.fill();

    // Subtle outline
    ctx.strokeStyle = 'rgba(255,255,255,0.18)';
    ctx.lineWidth = 1;
    this._roundRect(ctx, -hw, -hh, vw, vh * scaleX, 6);
    ctx.stroke();

    // Windshield
    ctx.fillStyle = 'rgba(255,255,255,0.22)';
    this._roundRect(ctx, -hw + 5, -hh + 8, vw - 10, 15, 3);
    ctx.fill();

    // Rear window
    ctx.fillStyle = 'rgba(255,255,255,0.12)';
    this._roundRect(ctx, -hw + 6, hh - 20, vw - 12, 12, 2);
    ctx.fill();

    // Wheels (4 corners)
    ctx.fillStyle = '#111827';
    const ww = 6;
    const wl = 11;
    const offsets = [
      [-hw - 2, -hh + 10],
      [hw - ww + 2, -hh + 10],
      [-hw - 2, hh - 10 - wl],
      [hw - ww + 2, hh - 10 - wl],
    ];
    for (const [ox, oy] of offsets) {
      this._roundRect(ctx, ox, oy, ww, wl, 1.5);
      ctx.fill();
    }

    // Front direction indicator (small triangle)
    ctx.fillStyle = 'rgba(255,255,255,0.50)';
    ctx.beginPath();
    ctx.moveTo(0, -hh + 4);
    ctx.lineTo(-5, -hh + 13);
    ctx.lineTo(5, -hh + 13);
    ctx.closePath();
    ctx.fill();

    // Crush damage marks
    if (damaged) {
      ctx.fillStyle = 'rgba(0,0,0,0.30)';
      ctx.fillRect(-hw + 3, hh - 7, vw - 6, 5);
      ctx.strokeStyle = 'rgba(255,255,255,0.15)';
      ctx.lineWidth = 0.7;
      for (let i = 0; i < 3; i++) {
        const lx = -hw + 6 + i * ((vw - 12) / 2);
        ctx.beginPath();
        ctx.moveTo(lx, hh - 7);
        ctx.lineTo(lx + 4, hh - 2);
        ctx.stroke();
      }
    }

    ctx.restore();

    // Label above vehicle
    ctx.fillStyle = '#cbd5e1';
    ctx.font = 'bold 11px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(label, x, y - vw / 2 - 14);
  }

  // --------------------------------------------------- draw: impact effects

  _drawImpactEffect(cx, cy, t) {
    const ctx = this.ctx;

    // Central radial flash
    if (t < 0.55) {
      const flashAlpha = Math.max(0, 1 - t / 0.55);
      const flashR = 10 + t * 55;
      const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, flashR);
      grad.addColorStop(0, 'rgba(255, 220, 60, ' + flashAlpha + ')');
      grad.addColorStop(0.45, 'rgba(249, 115, 22, ' + (flashAlpha * 0.5) + ')');
      grad.addColorStop(1, 'rgba(249, 115, 22, 0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(cx, cy, flashR, 0, Math.PI * 2);
      ctx.fill();
    }

    // Starburst spikes
    if (t < 0.5) {
      const spikeAlpha = 1 - t / 0.5;
      ctx.strokeStyle = 'rgba(255, 230, 80, ' + spikeAlpha + ')';
      ctx.lineWidth = 2;
      const innerR = 6;
      const outerR = 16 + t * 45;
      for (let i = 0; i < 10; i++) {
        const angle = (i / 10) * Math.PI * 2 + t * 3;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(angle) * innerR, cy + Math.sin(angle) * innerR);
        ctx.lineTo(cx + Math.cos(angle) * outerR, cy + Math.sin(angle) * outerR);
        ctx.stroke();
      }
    }

    // Flying spark particles
    for (const spark of this.sparks) {
      if (t > spark.life) continue;
      const p = t / spark.life;
      const sx = cx + Math.cos(spark.angle) * spark.speed * t;
      const sy = cy + Math.sin(spark.angle) * spark.speed * t + t * t * 30;
      const sr = spark.size * (1 - p * 0.6);
      const sa = Math.max(0, 1 - p);

      ctx.save();
      ctx.globalAlpha = sa;
      ctx.fillStyle = spark.bright ? this.colors.spark : this.colors.impact;
      ctx.shadowColor = spark.bright ? this.colors.spark : this.colors.impact;
      ctx.shadowBlur = 6;
      ctx.beginPath();
      ctx.arc(sx, sy, sr, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }
  }

  _drawImpactText(alpha) {
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha = Math.max(0, Math.min(1, alpha));
    ctx.font = 'bold 30px system-ui, sans-serif';
    ctx.fillStyle = '#ffffff';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.shadowColor = this.colors.impact;
    ctx.shadowBlur = 25;
    ctx.fillText('IMPACT', this.cx, this.cy - 80);
    ctx.shadowBlur = 0;
    ctx.restore();
  }

  // -------------------------------------------------------- draw: speedometer

  _drawSpeedometer(cx, cy, speedMph, label, color) {
    const ctx = this.ctx;
    const r = 40;

    // Background disc
    ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();

    // Colored ring
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();

    // Speed arc (fills proportionally, max display 70 mph)
    const frac = Math.min(Math.abs(speedMph) / 70, 1.0);
    const arcStart = Math.PI * 0.75;
    const arcEnd = arcStart + frac * Math.PI * 1.5;
    ctx.strokeStyle = color;
    ctx.lineWidth = 4;
    ctx.lineCap = 'round';
    ctx.beginPath();
    ctx.arc(cx, cy, r - 7, arcStart, arcEnd);
    ctx.stroke();
    ctx.lineCap = 'butt';

    // Speed number
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 17px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(Math.round(Math.abs(speedMph)).toString(), cx, cy - 4);

    // MPH unit
    ctx.fillStyle = '#94a3b8';
    ctx.font = '9px system-ui, sans-serif';
    ctx.fillText('MPH', cx, cy + 12);

    // Label
    ctx.fillStyle = color;
    ctx.font = 'bold 10px system-ui, sans-serif';
    ctx.fillText(label, cx, cy + 25);
  }

  // ----------------------------------------------------- draw: results overlay

  _drawResultsOverlay(v1x, v2x, alpha) {
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha = alpha;

    // Delta-V arrows
    this._drawDeltaVArrow(v1x, this.cy - 50, this.dv1, this.colors.v1, -1);
    this._drawDeltaVArrow(v2x, this.cy - 50, this.dv2, this.colors.v2, 1);

    // Center results panel
    const px = this.cx;
    const py = 26;
    const pw = 180;
    const ph = 60;

    ctx.fillStyle = 'rgba(15, 23, 42, 0.92)';
    this._roundRect(ctx, px - pw / 2, py - 16, pw, ph, 8);
    ctx.fill();
    ctx.strokeStyle = this.colors.impact;
    ctx.lineWidth = 1.5;
    this._roundRect(ctx, px - pw / 2, py - 16, pw, ph, 8);
    ctx.stroke();

    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Peak Force', px, py);

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 15px system-ui, sans-serif';
    ctx.fillText(this._fmtForce(this.peakForce), px, py + 17);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px system-ui, sans-serif';
    ctx.fillText(
      'Crush: ' + (this.crush * 12).toFixed(1) + ' in  (' +
      this.crush.toFixed(2) + ' ft)', px, py + 33
    );

    ctx.restore();
  }

  _drawDeltaVArrow(x, y, deltaMph, color, dir) {
    const ctx = this.ctx;
    const arrowLen = Math.min(deltaMph * 2.4, 60);

    // Shaft
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + dir * arrowLen, y);
    ctx.stroke();

    // Arrowhead
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x + dir * arrowLen, y);
    ctx.lineTo(x + dir * (arrowLen - 9), y - 5);
    ctx.lineTo(x + dir * (arrowLen - 9), y + 5);
    ctx.closePath();
    ctx.fill();

    // Label
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 12px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(
      '\u0394V ' + deltaMph.toFixed(1) + ' mph',
      x + dir * arrowLen / 2, y - 11
    );
  }

  // ------------------------------------------------------- draw: info panel

  _drawInfoPanel(t) {
    const ctx = this.ctx;
    const px = 12;
    const py = 10;

    ctx.fillStyle = 'rgba(15, 23, 42, 0.78)';
    this._roundRect(ctx, px, py, 150, 24, 5);
    ctx.fill();

    let phase;
    if (t <= 0.40) phase = 'Approaching...';
    else if (t <= 0.50) phase = 'Impact';
    else if (t <= 0.80) phase = 'Post-Impact';
    else phase = 'Results';

    ctx.fillStyle = '#e2e8f0';
    ctx.font = '11px system-ui, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(phase, px + 8, py + 16);

    // Progress bar
    const bx = px + 96;
    const by = py + 8;
    const bw = 46;
    const bh = 6;
    ctx.fillStyle = 'rgba(255,255,255,0.10)';
    this._roundRect(ctx, bx, by, bw, bh, 3);
    ctx.fill();
    ctx.fillStyle = this.colors.impact;
    this._roundRect(ctx, bx, by, bw * t, bh, 3);
    ctx.fill();
  }

  // ------------------------------------------------------- draw: replay button

  _drawReplayButton() {
    const ctx = this.ctx;
    const bx = this.width / 2;
    const by = this.height - 28;
    const bw = 110;
    const bh = 30;

    ctx.fillStyle = 'rgba(59, 130, 246, 0.92)';
    this._roundRect(ctx, bx - bw / 2, by - bh / 2, bw, bh, 7);
    ctx.fill();

    ctx.strokeStyle = 'rgba(255,255,255,0.25)';
    ctx.lineWidth = 1;
    this._roundRect(ctx, bx - bw / 2, by - bh / 2, bw, bh, 7);
    ctx.stroke();

    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 13px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText('\u25B6  Replay', bx, by);

    // Store bounds for click detection
    this._replayBounds = {
      x: bx - bw / 2,
      y: by - bh / 2,
      w: bw,
      h: bh,
    };

    // Attach click listener once
    if (!this._replayListenerAttached) {
      this._replayListenerAttached = true;
      this.canvas.style.cursor = 'default';
      this.canvas.addEventListener('click', (e) => this._handleClick(e));
      this.canvas.addEventListener('mousemove', (e) => this._handleHover(e));
    }
  }

  _handleClick(e) {
    if (!this._replayBounds || this.animating) return;
    const pt = this._canvasPoint(e);
    const b = this._replayBounds;
    if (pt.x >= b.x && pt.x <= b.x + b.w && pt.y >= b.y && pt.y <= b.y + b.h) {
      this.animate(this.results, this.params);
    }
  }

  _handleHover(e) {
    if (!this._replayBounds || this.animating) {
      this.canvas.style.cursor = 'default';
      return;
    }
    const pt = this._canvasPoint(e);
    const b = this._replayBounds;
    const inside = pt.x >= b.x && pt.x <= b.x + b.w &&
                   pt.y >= b.y && pt.y <= b.y + b.h;
    this.canvas.style.cursor = inside ? 'pointer' : 'default';
  }

  _canvasPoint(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left) * (this.width / rect.width),
      y: (e.clientY - rect.top) * (this.height / rect.height),
    };
  }

  // ------------------------------------------------------------ idle scene

  _drawIdle() {
    const ctx = this.ctx;
    this.cx = this.width * 0.50;
    this.cy = this.height * 0.48;
    this._drawRoad();

    this._drawVehicle(
      this.width * 0.28, this.cy - 4, 90,
      this.carW, this.carH, this.colors.v1,
      'Vehicle 1', 1, false
    );
    this._drawVehicle(
      this.width * 0.72, this.cy + 4, -90,
      this.carW, this.carH, this.colors.v2,
      'Vehicle 2', 1, false
    );

    ctx.fillStyle = 'rgba(255,255,255,0.55)';
    ctx.font = '15px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Configure parameters and run simulation', this.width / 2, this.height - 18);
  }

  // --------------------------------------------------------- easing functions

  _easeInOut(t) {
    return t < 0.5
      ? 4 * t * t * t
      : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  _easeOut(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  // ------------------------------------------------------------ helpers

  _roundRect(ctx, x, y, w, h, r) {
    r = Math.min(r, w / 2, h / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.arcTo(x + w, y, x + w, y + r, r);
    ctx.lineTo(x + w, y + h - r);
    ctx.arcTo(x + w, y + h, x + w - r, y + h, r);
    ctx.lineTo(x + r, y + h);
    ctx.arcTo(x, y + h, x, y + h - r, r);
    ctx.lineTo(x, y + r);
    ctx.arcTo(x, y, x + r, y, r);
    ctx.closePath();
  }

  _fmtForce(lb) {
    if (lb >= 1000) return (lb / 1000).toFixed(1) + 'k lb';
    return Math.round(lb) + ' lb';
  }
}
