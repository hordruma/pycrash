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

    async runSync() {
      this.loading = true;
      this.error = null;
      this.results = null;

      try {
        const resp = await fetch('/api/v1/simulate/sdof/sync', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.buildPayload()),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Request failed with status ${resp.status}`);
        }

        this.results = await resp.json();
        this.$nextTick(() => this.plotResults());
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
      } finally {
        this.loading = false;
      }
    },

    async runAsync() {
      this.loading = true;
      this.error = null;
      this.results = null;
      this.jobId = null;

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
        margin: { t: 40, r: 20, b: 50, l: 60 },
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        xaxis: { gridcolor: '#e5e7eb' },
        yaxis: { gridcolor: '#e5e7eb' },
      };

      if (this.results && this.results.model_data) {
        const md = this.results.model_data;

        // Velocity vs Time
        const velDiv = document.getElementById('velocity-chart');
        if (velDiv) {
          Plotly.newPlot(
            velDiv,
            [
              {
                x: md.t,
                y: md.v1,
                mode: 'lines',
                name: 'Vehicle 1',
                line: { color: '#3b82f6', width: 2 },
              },
              {
                x: md.t,
                y: md.v2,
                mode: 'lines',
                name: 'Vehicle 2',
                line: { color: '#ef4444', width: 2 },
              },
            ],
            {
              ...baseLayout,
              title: 'Velocity vs Time',
              xaxis: { ...baseLayout.xaxis, title: 'Time (s)' },
              yaxis: { ...baseLayout.yaxis, title: 'Velocity (ft/s)' },
            },
            plotConfig
          );
        }

        // Force vs Time
        const forceDiv = document.getElementById('force-chart');
        if (forceDiv) {
          Plotly.newPlot(
            forceDiv,
            [
              {
                x: md.t,
                y: md.springF,
                mode: 'lines',
                name: 'Spring Force',
                line: { color: '#22c55e', width: 2 },
              },
            ],
            {
              ...baseLayout,
              title: 'Impact Force',
              xaxis: { ...baseLayout.xaxis, title: 'Time (s)' },
              yaxis: { ...baseLayout.yaxis, title: 'Force (lb)' },
            },
            plotConfig
          );
        }

        // Crush vs Time
        const crushDiv = document.getElementById('crush-chart');
        if (crushDiv) {
          Plotly.newPlot(
            crushDiv,
            [
              {
                x: md.t,
                y: md.dx,
                mode: 'lines',
                name: 'Crush',
                line: { color: '#f97316', width: 2 },
              },
            ],
            {
              ...baseLayout,
              title: 'Crush Displacement',
              xaxis: { ...baseLayout.xaxis, title: 'Time (s)' },
              yaxis: { ...baseLayout.yaxis, title: 'Crush (ft)' },
            },
            plotConfig
          );
        }
      } else {
        // Sync results: clear charts since no time-series data is available
        ['velocity-chart', 'force-chart', 'crush-chart'].forEach((id) => {
          const el = document.getElementById(id);
          if (el) {
            Plotly.purge(el);
          }
        });
      }
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

      ['velocity-chart', 'force-chart', 'crush-chart'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
          Plotly.purge(el);
        }
      });
    },
  };
}
