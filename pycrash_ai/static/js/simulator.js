function simulatorApp() {
  return {
    // Form inputs
    w1: 3400,
    w2: 3000,
    v1: 35,
    v2: 0,
    v1_brake: 0,
    v2_brake: 0,
    k: 50000,
    cor: 0.15,
    tstop: 0.5,

    // State
    loading: false,
    error: null,
    results: null,
    jobId: null,
    animation: null,

    initAnimation() {
      this.$nextTick(() => {
        const canvas = document.getElementById('crash-canvas');
        if (canvas && typeof CrashAnimation !== 'undefined') {
          this.animation = new CrashAnimation(canvas);
          this.animation.drawIdle();
        }
      });
    },

    buildPayload() {
      return {
        w1: Number(this.w1),
        w2: Number(this.w2),
        v1: Number(this.v1),
        v2: Number(this.v2),
        v1_brake: Number(this.v1_brake),
        v2_brake: Number(this.v2_brake),
        k: Number(this.k),
        cor: Number(this.cor),
        tstop: Number(this.tstop),
      };
    },

    async runAndAnimate() {
      this.loading = true;
      this.error = null;
      this.results = null;

      try {
        const payload = this.buildPayload();
        const resp = await fetch('/api/v1/simulate/sdof/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Request failed with status ${resp.status}`);
        }

        this.results = await resp.json();

        // Play animation
        if (this.animation) {
          this.animation.animate(this.results, payload);
        }
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
      } finally {
        this.loading = false;
      }
    },

    replayAnimation() {
      if (this.animation && this.results) {
        this.animation.animate(this.results, this.buildPayload());
      }
    },

    async runSync() {
      return this.runAndAnimate();
    },

    async runAsync() {
      this.loading = true;
      this.error = null;

      try {
        const resp = await fetch('/api/v1/simulate/sdof', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.buildPayload()),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Request failed with status ${resp.status}`);
        }

        const data = await resp.json();
        this.jobId = data.job_id;

        const result = await this.pollJob(this.jobId);
        this.results = result;
        this.$nextTick(() => this.plotResults());
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
      } finally {
        this.loading = false;
      }
    },

    async pollJob(jobId) {
      while (true) {
        await new Promise((resolve) => setTimeout(resolve, 1000));

        const resp = await fetch(`/api/v1/simulate/${jobId}`);
        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Polling failed with status ${resp.status}`);
        }

        const data = await resp.json();

        if (data.status === 'complete' || data.status === 'completed') {
          return data.results || data;
        }

        if (data.status === 'failed' || data.status === 'error') {
          throw new Error(data.error || 'Simulation failed');
        }
      }
    },

    plotResults() {
      const plotConfig = {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ['lasso2d', 'select2d'],
      };

      const baseLayout = {
        font: { family: 'Inter, system-ui, sans-serif', size: 12 },
        margin: { t: 20, r: 20, b: 50, l: 60 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        xaxis: { gridcolor: '#e5e7eb' },
        yaxis: { gridcolor: '#e5e7eb' },
      };

      if (this.results && this.results.model_data) {
        const md = this.results.model_data;

        const velDiv = document.getElementById('velocity-chart');
        if (velDiv) {
          Plotly.newPlot(velDiv, [
            { x: md.t, y: md.v1, mode: 'lines', name: 'Car 1', line: { color: '#3b82f6', width: 2 } },
            { x: md.t, y: md.v2, mode: 'lines', name: 'Car 2', line: { color: '#ef4444', width: 2 } },
          ], { ...baseLayout, xaxis: { ...baseLayout.xaxis, title: 'Time (s)' }, yaxis: { ...baseLayout.yaxis, title: 'Velocity (ft/s)' } }, plotConfig);
        }

        const forceDiv = document.getElementById('force-chart');
        if (forceDiv) {
          Plotly.newPlot(forceDiv, [
            { x: md.t, y: md.springF, mode: 'lines', name: 'Force', line: { color: '#22c55e', width: 2 } },
          ], { ...baseLayout, xaxis: { ...baseLayout.xaxis, title: 'Time (s)' }, yaxis: { ...baseLayout.yaxis, title: 'Force (lb)' } }, plotConfig);
        }

        const crushDiv = document.getElementById('crush-chart');
        if (crushDiv) {
          Plotly.newPlot(crushDiv, [
            { x: md.t, y: md.dx, mode: 'lines', name: 'Crush', line: { color: '#f97316', width: 2 } },
          ], { ...baseLayout, xaxis: { ...baseLayout.xaxis, title: 'Time (s)' }, yaxis: { ...baseLayout.yaxis, title: 'Crush (ft)' } }, plotConfig);
        }
      }
    },

    // Severity labels for delta-V
    getSeverityLabel(dv) {
      if (!dv) return '';
      if (dv < 5) return 'Parking lot bump';
      if (dv < 10) return 'Minor fender bender';
      if (dv < 15) return 'Moderate collision';
      if (dv < 25) return 'Serious crash';
      if (dv < 40) return 'Severe impact';
      return 'Catastrophic';
    },

    // Fun force comparisons
    formatForce(lb) {
      if (!lb) return '--';
      if (lb >= 1000) return (lb / 1000).toFixed(1) + 'k lb';
      return Math.round(lb) + ' lb';
    },

    getForceComparison(lb) {
      if (!lb) return '';
      const elephants = lb / 12000;
      if (elephants >= 1) return `Like ${elephants.toFixed(1)} elephants`;
      const fridges = lb / 300;
      if (fridges >= 1) return `Like ${Math.round(fridges)} refrigerators`;
      return 'About a heavy push';
    },

    getGForceComparison(g) {
      if (!g) return '';
      if (g < 2) return 'Roller coaster level';
      if (g < 5) return 'Fighter jet turn';
      if (g < 15) return 'Race car crash';
      if (g < 30) return 'Hard to survive';
      return 'Extreme';
    },

    reset() {
      this.w1 = 3400;
      this.w2 = 3000;
      this.v1 = 35;
      this.v2 = 0;
      this.v1_brake = 0;
      this.v2_brake = 0;
      this.k = 50000;
      this.cor = 0.15;
      this.tstop = 0.5;
      this.loading = false;
      this.error = null;
      this.results = null;
      this.jobId = null;

      if (this.animation) this.animation.drawIdle();

      ['velocity-chart', 'force-chart', 'crush-chart'].forEach((id) => {
        const el = document.getElementById(id);
        if (el && typeof Plotly !== 'undefined') Plotly.purge(el);
      });
    },
  };
}
