function monteCarloApp() {
  return {
    // Base config
    base: {
      w1: 3400,
      w2: 3000,
      v1: 35,
      v2: 0,
      cor: 0.15,
      k: 50000,
      tstop: 0.5,
      v1_brake: 0,
      v2_brake: 0,
    },

    // Variations
    variations: [],
    n_runs: 1000,

    // State
    loading: false,
    error: null,
    results: null,
    jobId: null,
    progress: 0,

    addVariation() {
      this.variations.push({
        parameter: 'v1',
        min_value: 30,
        max_value: 40,
        distribution: 'uniform',
      });
    },

    removeVariation(i) {
      this.variations.splice(i, 1);
    },

    async runMC() {
      if (this.variations.length === 0) {
        this.error = 'Add at least one parameter variation before running.';
        return;
      }

      this.loading = true;
      this.error = null;
      this.results = null;
      this.jobId = null;
      this.progress = 0;

      try {
        const payload = {
          base_config: { ...this.base },
          variations: this.variations.map((v) => ({
            parameter: v.parameter,
            min_value: Number(v.min_value),
            max_value: Number(v.max_value),
            distribution: v.distribution,
          })),
          n_runs: Number(this.n_runs),
        };

        // Ensure base_config values are numbers
        for (const key of Object.keys(payload.base_config)) {
          payload.base_config[key] = Number(payload.base_config[key]);
        }

        const resp = await fetch('/api/v1/montecarlo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Request failed with status ${resp.status}`);
        }

        const data = await resp.json();
        this.jobId = data.job_id;

        const result = await this.pollMC(this.jobId);
        this.results = result;
        this.$nextTick(() => this.plotResults());
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
      } finally {
        this.loading = false;
      }
    },

    async pollMC(jobId) {
      while (true) {
        await new Promise((resolve) => setTimeout(resolve, 2000));

        const resp = await fetch(`/api/v1/montecarlo/${jobId}`);
        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Polling failed with status ${resp.status}`);
        }

        const data = await resp.json();

        // Update progress
        if (data.completed_runs != null && data.total_runs != null && data.total_runs > 0) {
          this.progress = Math.round((data.completed_runs / data.total_runs) * 100);
        } else if (data.results && data.results.completed_runs != null) {
          const r = data.results;
          if (r.total_runs > 0) {
            this.progress = Math.round((r.completed_runs / r.total_runs) * 100);
          }
        }

        if (data.status === 'complete' || data.status === 'completed') {
          this.progress = 100;
          return data.results || data;
        }

        if (data.status === 'failed' || data.status === 'error') {
          throw new Error(data.error || 'Monte Carlo simulation failed');
        }
      }
    },

    plotResults() {
      if (!this.results) return;

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
        bargap: 0.05,
        showlegend: false,
      };

      this.plotHistogram(
        'mc-dv1-hist',
        this.results.delta_v1_mph,
        'Delta-V Vehicle 1 (mph)',
        '#3b82f6',
        baseLayout,
        plotConfig
      );

      this.plotHistogram(
        'mc-dv2-hist',
        this.results.delta_v2_mph,
        'Delta-V Vehicle 2 (mph)',
        '#ef4444',
        baseLayout,
        plotConfig
      );

      this.plotHistogram(
        'mc-crush-hist',
        this.results.peak_crush_ft,
        'Peak Crush (ft)',
        '#f97316',
        baseLayout,
        plotConfig
      );
    },

    plotHistogram(divId, stat, title, color, baseLayout, plotConfig) {
      const el = document.getElementById(divId);
      if (!el || !stat || !stat.values) return;

      const values = stat.values;
      const mean = stat.mean;
      const p5 = stat.p5;
      const p95 = stat.p95;

      const traces = [
        {
          x: values,
          type: 'histogram',
          nbinsx: 30,
          marker: { color: color, opacity: 0.7 },
          name: title,
        },
      ];

      // Compute approximate y-max for annotation lines
      const yMax = Math.ceil(values.length / 15);

      const shapes = [
        // Mean line
        {
          type: 'line',
          x0: mean,
          x1: mean,
          y0: 0,
          y1: 1,
          yref: 'paper',
          line: { color: '#111827', width: 2, dash: 'solid' },
        },
        // 5th percentile
        {
          type: 'line',
          x0: p5,
          x1: p5,
          y0: 0,
          y1: 1,
          yref: 'paper',
          line: { color: '#6b7280', width: 1.5, dash: 'dash' },
        },
        // 95th percentile
        {
          type: 'line',
          x0: p95,
          x1: p95,
          y0: 0,
          y1: 1,
          yref: 'paper',
          line: { color: '#6b7280', width: 1.5, dash: 'dash' },
        },
      ];

      const annotations = [
        {
          x: mean,
          y: 1,
          yref: 'paper',
          text: `Mean: ${mean.toFixed(2)}`,
          showarrow: false,
          yanchor: 'bottom',
          font: { size: 10, color: '#111827' },
        },
        {
          x: p5,
          y: 0.92,
          yref: 'paper',
          text: `5th: ${p5.toFixed(2)}`,
          showarrow: false,
          yanchor: 'bottom',
          font: { size: 10, color: '#6b7280' },
        },
        {
          x: p95,
          y: 0.92,
          yref: 'paper',
          text: `95th: ${p95.toFixed(2)}`,
          showarrow: false,
          yanchor: 'bottom',
          font: { size: 10, color: '#6b7280' },
        },
      ];

      Plotly.newPlot(
        el,
        traces,
        {
          ...baseLayout,
          title: title,
          xaxis: { ...baseLayout.xaxis, title: title },
          yaxis: { ...baseLayout.yaxis, title: 'Count' },
          shapes: shapes,
          annotations: annotations,
        },
        plotConfig
      );
    },

    reset() {
      this.base = {
        w1: 3400,
        w2: 3000,
        v1: 35,
        v2: 0,
        cor: 0.15,
        k: 50000,
        tstop: 0.5,
        v1_brake: 0,
        v2_brake: 0,
      };
      this.variations = [];
      this.n_runs = 1000;
      this.loading = false;
      this.error = null;
      this.results = null;
      this.jobId = null;
      this.progress = 0;

      ['mc-dv1-hist', 'mc-dv2-hist', 'mc-crush-hist'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) {
          Plotly.purge(el);
        }
      });
    },
  };
}
