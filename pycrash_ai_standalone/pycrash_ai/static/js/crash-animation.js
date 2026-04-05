/**
 * CrashAnimation — Canvas-based 2D top-down crash visualization
 * Renders an animated collision between two vehicles using SDOF results.
 */
class CrashAnimation {
  constructor(canvas, options = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.width = canvas.width;
    this.height = canvas.height;
    this.duration = options.duration || 3000;
    this.colors = {
      v1: '#3b82f6',
      v2: '#ef4444',
      road: '#374151',
      lane: '#fbbf24',
      grass: '#22c55e',
      impact: '#f97316',
      spark: '#fbbf24',
    };
    this.animating = false;
    this.frameId = null;
    this.results = null;
    this.params = null;
    this.onComplete = options.onComplete || null;

    // Vehicle dimensions (pixels)
    this.carW = 36;
    this.carH = 70;
  }

  animate(results, params) {
    this.stop();
    this.results = results;
    this.params = params;

    // Pre-compute physics values
    this.v1_init_mph = params.v1 || 35;
    this.v2_init_mph = params.v2 || 0;
    this.v1_final_fps = results.v1_final_fps || 0;
    this.v2_final_fps = results.v2_final_fps || 0;
    this.dv1 = results.delta_v1_mph || 0;
    this.dv2 = results.delta_v2_mph || 0;
    this.crush = results.peak_crush_ft || 0;
    this.peakForce = results.peak_force_lb || 0;

    // Impact zone center
    this.cx = this.width * 0.5;
    this.cy = this.height * 0.48;

    // Start/end x-positions
    this.v1Start = this.width * 0.12;
    this.v2Start = this.width * 0.88;
    this.v1Impact = this.cx - this.carH / 2 - 2;
    this.v2Impact = this.cx + this.carH / 2 + 2;

    // Post-impact drift distances (proportional to final speed)
    const maxDrift = this.width * 0.18;
    const v1f_mph = this.v1_final_fps * 0.681818;
    const v2f_mph = this.v2_final_fps * 0.681818;
    const maxSpeed = Math.max(this.v1_init_mph, 1);
    this.v1End = this.v1Impact - (v1f_mph / maxSpeed) * maxDrift * 0.3;
    this.v2End = this.v2Impact + (v2f_mph / maxSpeed) * maxDrift;

    // Sparks
    this.sparks = [];
    for (let i = 0; i < 14; i++) {
      const angle = (Math.PI * 2 * i) / 14 + (Math.random() - 0.5) * 0.4;
      this.sparks.push({
        angle,
        speed: 40 + Math.random() * 80,
        size: 2 + Math.random() * 4,
        life: 0.6 + Math.random() * 0.4,
        color: Math.random() > 0.4 ? this.colors.spark : this.colors.impact,
      });
    }

    // Shake
    this.shakeX = 0;
    this.shakeY = 0;

    this.startTime = performance.now();
    this.animating = true;
    this._loop(this.startTime);
  }

  stop() {
    this.animating = false;
    if (this.frameId) {
      cancelAnimationFrame(this.frameId);
      this.frameId = null;
    }
  }

  reset() {
    this.stop();
    this.results = null;
    this.params = null;
    this._drawIdle();
  }

  _loop(timestamp) {
    if (!this.animating) return;
    const elapsed = timestamp - this.startTime;
    const t = Math.min(elapsed / this.duration, 1);

    this._drawFrame(t);

    if (t < 1) {
      this.frameId = requestAnimationFrame((ts) => this._loop(ts));
    } else {
      this.animating = false;
      if (this.onComplete) this.onComplete();
    }
  }

  _drawFrame(t) {
    const ctx = this.ctx;
    ctx.save();

    // Screen shake during impact
    if (t > 0.38 && t < 0.55) {
      const shakeIntensity = Math.sin((t - 0.38) * 60) * 4 * (1 - (t - 0.38) / 0.17);
      this.shakeX = shakeIntensity * (Math.random() - 0.5);
      this.shakeY = shakeIntensity * (Math.random() - 0.5);
    } else {
      this.shakeX = 0;
      this.shakeY = 0;
    }
    ctx.translate(this.shakeX, this.shakeY);

    // Background
    this._drawRoad();

    // Compute vehicle positions
    let v1x, v2x, crushScale1 = 1, crushScale2 = 1;

    if (t < 0.4) {
      // Phase 1: Approach
      const p = this._easeInOut(t / 0.4);
      v1x = this.v1Start + (this.v1Impact - this.v1Start) * p;
      v2x = this.v2Start + (this.v2Impact - this.v2Start) * p;
    } else if (t < 0.5) {
      // Phase 2: Impact
      const p = (t - 0.4) / 0.1;
      v1x = this.v1Impact;
      v2x = this.v2Impact;
      const crushAmount = Math.sin(p * Math.PI) * 0.12;
      crushScale1 = 1 - crushAmount;
      crushScale2 = 1 - crushAmount;
    } else if (t < 0.8) {
      // Phase 3: Separation
      const p = this._easeOut((t - 0.5) / 0.3);
      v1x = this.v1Impact + (this.v1End - this.v1Impact) * p;
      v2x = this.v2Impact + (this.v2End - this.v2Impact) * p;
    } else {
      // Phase 4: Rest + results
      v1x = this.v1End;
      v2x = this.v2End;
    }

    // Draw vehicles
    this._drawVehicle(v1x, this.cy, 90, this.carW, this.carH, this.colors.v1,
      `${this.params.w1?.toLocaleString() || '3,400'} lb`, crushScale1, t > 0.5);
    this._drawVehicle(v2x, this.cy, -90, this.carW, this.carH, this.colors.v2,
      `${this.params.w2?.toLocaleString() || '3,000'} lb`, crushScale2, t > 0.5);

    // Impact effects
    if (t >= 0.38 && t < 0.6) {
      const impactT = (t - 0.38) / 0.22;
      this._drawImpactEffect(this.cx, this.cy, impactT);
    }

    // Impact flash text
    if (t >= 0.4 && t < 0.55) {
      const fadeT = (t - 0.4) / 0.15;
      ctx.save();
      ctx.globalAlpha = 1 - fadeT;
      ctx.font = 'bold 28px system-ui';
      ctx.fillStyle = '#fff';
      ctx.textAlign = 'center';
      ctx.shadowColor = this.colors.impact;
      ctx.shadowBlur = 20;
      ctx.fillText('IMPACT!', this.cx, this.cy - 60);
      ctx.restore();
    }

    // Speedometers
    const v1Speed = this._getCurrentSpeed(t, this.v1_init_mph, this.v1_final_fps * 0.681818);
    const v2Speed = this._getCurrentSpeed(t, this.v2_init_mph, this.v2_final_fps * 0.681818);
    this._drawSpeedBadge(60, this.height - 45, v1Speed, 'Car 1', this.colors.v1);
    this._drawSpeedBadge(this.width - 60, this.height - 45, v2Speed, 'Car 2', this.colors.v2);

    // Results overlay (phase 4)
    if (t > 0.8) {
      const fadeIn = Math.min((t - 0.8) / 0.15, 1);
      this._drawResults(fadeIn, v1x, v2x);
    }

    ctx.restore();
  }

  _drawRoad() {
    const ctx = this.ctx;
    // Sky/grass
    ctx.fillStyle = '#e8f5e9';
    ctx.fillRect(0, 0, this.width, this.height);

    // Road surface
    const roadTop = this.cy - 65;
    const roadH = 130;
    ctx.fillStyle = this.colors.road;
    ctx.beginPath();
    ctx.roundRect(20, roadTop, this.width - 40, roadH, 8);
    ctx.fill();

    // Road edge lines
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.moveTo(30, roadTop + 4);
    ctx.lineTo(this.width - 30, roadTop + 4);
    ctx.moveTo(30, roadTop + roadH - 4);
    ctx.lineTo(this.width - 30, roadTop + roadH - 4);
    ctx.stroke();

    // Center line (dashed yellow)
    ctx.strokeStyle = this.colors.lane;
    ctx.lineWidth = 3;
    ctx.setLineDash([20, 15]);
    ctx.beginPath();
    ctx.moveTo(30, this.cy);
    ctx.lineTo(this.width - 30, this.cy);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  _drawVehicle(x, y, headingDeg, w, h, color, label, scaleX, damaged) {
    const ctx = this.ctx;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate((headingDeg * Math.PI) / 180);

    // Shadow
    ctx.fillStyle = 'rgba(0,0,0,0.15)';
    ctx.beginPath();
    ctx.roundRect(-w / 2 + 3, -h / 2 * scaleX + 3, w, h * scaleX, 6);
    ctx.fill();

    // Body
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(-w / 2, -h / 2 * scaleX, w, h * scaleX, 6);
    ctx.fill();

    // Windshield
    ctx.fillStyle = 'rgba(255,255,255,0.3)';
    ctx.beginPath();
    ctx.roundRect(-w / 2 + 5, -h / 2 * scaleX + 8, w - 10, 16, 3);
    ctx.fill();

    // Damage indicator (crumpled front)
    if (damaged && scaleX < 1) {
      ctx.fillStyle = 'rgba(0,0,0,0.3)';
      ctx.fillRect(-w / 2 + 2, h / 2 * scaleX - 8, w - 4, 6);
    }

    // Wheels
    ctx.fillStyle = '#1a1a1a';
    const ww = 6, wh = 12;
    // Front left/right
    ctx.fillRect(-w / 2 - 2, -h / 2 * scaleX + 10, ww, wh);
    ctx.fillRect(w / 2 - 4, -h / 2 * scaleX + 10, ww, wh);
    // Rear left/right
    ctx.fillRect(-w / 2 - 2, h / 2 * scaleX - 22, ww, wh);
    ctx.fillRect(w / 2 - 4, h / 2 * scaleX - 22, ww, wh);

    // Direction arrow at front
    ctx.fillStyle = 'rgba(255,255,255,0.6)';
    ctx.beginPath();
    ctx.moveTo(0, -h / 2 * scaleX + 4);
    ctx.lineTo(-6, -h / 2 * scaleX + 14);
    ctx.lineTo(6, -h / 2 * scaleX + 14);
    ctx.closePath();
    ctx.fill();

    ctx.restore();

    // Label above vehicle
    ctx.save();
    ctx.font = '11px system-ui';
    ctx.fillStyle = '#374151';
    ctx.textAlign = 'center';
    ctx.fillText(label, x, y - 50);
    ctx.restore();
  }

  _drawImpactEffect(x, y, t) {
    const ctx = this.ctx;

    // Starburst
    if (t < 0.5) {
      ctx.save();
      const starAlpha = 1 - t * 2;
      ctx.globalAlpha = starAlpha;
      const radius = 15 + t * 60;
      ctx.strokeStyle = this.colors.impact;
      ctx.lineWidth = 3;
      for (let i = 0; i < 8; i++) {
        const angle = (Math.PI * 2 * i) / 8;
        ctx.beginPath();
        ctx.moveTo(x + Math.cos(angle) * 5, y + Math.sin(angle) * 5);
        ctx.lineTo(x + Math.cos(angle) * radius, y + Math.sin(angle) * radius);
        ctx.stroke();
      }
      ctx.restore();
    }

    // Sparks
    this.sparks.forEach((spark) => {
      if (t > spark.life) return;
      const p = t / spark.life;
      const sx = x + Math.cos(spark.angle) * spark.speed * t;
      const sy = y + Math.sin(spark.angle) * spark.speed * t;
      const alpha = 1 - p;
      const size = spark.size * (1 - p * 0.5);

      ctx.save();
      ctx.globalAlpha = alpha;
      ctx.fillStyle = spark.color;
      ctx.shadowColor = spark.color;
      ctx.shadowBlur = 8;
      ctx.beginPath();
      ctx.arc(sx, sy, size, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    });
  }

  _drawSpeedBadge(x, y, speed, label, color) {
    const ctx = this.ctx;
    ctx.save();

    // Badge background
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.beginPath();
    ctx.roundRect(x - 42, y - 18, 84, 36, 8);
    ctx.fill();

    // Speed number
    ctx.font = 'bold 16px system-ui';
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.fillText(`${Math.round(speed)} mph`, x, y + 2);

    // Label
    ctx.font = '9px system-ui';
    ctx.fillStyle = '#aaa';
    ctx.fillText(label, x, y + 14);

    ctx.restore();
  }

  _drawResults(alpha, v1x, v2x) {
    const ctx = this.ctx;
    ctx.save();
    ctx.globalAlpha = alpha;

    // Delta-V arrows
    this._drawDeltaVArrow(v1x, this.cy - 70, this.dv1, this.colors.v1, 'left');
    this._drawDeltaVArrow(v2x, this.cy - 70, this.dv2, this.colors.v2, 'right');

    // Center info box
    const bx = this.cx - 80;
    const by = 12;
    ctx.fillStyle = 'rgba(0,0,0,0.75)';
    ctx.beginPath();
    ctx.roundRect(bx, by, 160, 54, 8);
    ctx.fill();

    ctx.font = 'bold 11px system-ui';
    ctx.fillStyle = '#fff';
    ctx.textAlign = 'center';
    ctx.fillText(`Peak Force: ${this._fmtForce(this.peakForce)}`, this.cx, by + 18);
    ctx.fillText(`Crush: ${this.crush.toFixed(2)} ft`, this.cx, by + 34);
    ctx.font = '10px system-ui';
    ctx.fillStyle = '#9ca3af';
    ctx.fillText('Click replay to run again', this.cx, by + 48);

    ctx.restore();
  }

  _drawDeltaVArrow(x, y, dv, color, direction) {
    const ctx = this.ctx;
    ctx.save();

    // Arrow
    const arrowLen = Math.min(dv * 2, 60);
    const dir = direction === 'left' ? -1 : 1;

    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x + arrowLen * dir, y);
    ctx.stroke();

    // Arrowhead
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(x + arrowLen * dir, y);
    ctx.lineTo(x + (arrowLen - 8) * dir, y - 5);
    ctx.lineTo(x + (arrowLen - 8) * dir, y + 5);
    ctx.closePath();
    ctx.fill();

    // Label
    ctx.font = 'bold 13px system-ui';
    ctx.fillStyle = color;
    ctx.textAlign = 'center';
    ctx.fillText(`ΔV ${dv.toFixed(1)} mph`, x + (arrowLen * dir) / 2, y - 10);

    ctx.restore();
  }

  _getCurrentSpeed(t, initMph, finalMph) {
    if (t < 0.4) return initMph;
    if (t < 0.5) {
      const p = (t - 0.4) / 0.1;
      return initMph + (finalMph - initMph) * p;
    }
    if (t < 0.8) {
      const p = (t - 0.5) / 0.3;
      return finalMph * (1 - p * 0.3);
    }
    return finalMph * 0.7;
  }

  _easeInOut(t) {
    return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
  }

  _easeOut(t) {
    return 1 - Math.pow(1 - t, 3);
  }

  _fmtForce(lb) {
    if (lb >= 1000) return `${(lb / 1000).toFixed(1)}k lb`;
    return `${Math.round(lb)} lb`;
  }

  drawIdle() {
    this._drawIdle();
  }

  _drawIdle() {
    const ctx = this.ctx;
    this._drawRoad();

    // Draw parked vehicles
    const v1x = this.width * 0.3;
    const v2x = this.width * 0.7;
    const cy = this.height * 0.48;

    this._drawVehicle(v1x, cy, 90, this.carW, this.carH, this.colors.v1, 'Car 1', 1, false);
    this._drawVehicle(v2x, cy, -90, this.carW, this.carH, this.colors.v2, 'Car 2', 1, false);

    // Prompt text
    ctx.save();
    ctx.font = '16px system-ui';
    ctx.fillStyle = 'rgba(255,255,255,0.7)';
    ctx.textAlign = 'center';
    ctx.fillText('Set up your crash and hit the button!', this.width / 2, this.height - 20);
    ctx.restore();
  }
}
