function visualizeApp() {
  return {
    // Vehicle 1
    v1: { x: 0, y: 0, heading: 0, length: 15, width: 6, label: 'Vehicle 1' },
    // Vehicle 2
    v2: { x: 20, y: 10, heading: 90, length: 15, width: 6, label: 'Vehicle 2' },
    // Impact point
    impactX: '',
    impactY: '',

    // State
    loading: false,
    error: null,

    buildPayload() {
      const payload = {
        vehicles: [
          {
            x: Number(this.v1.x),
            y: Number(this.v1.y),
            heading: Number(this.v1.heading),
            length: Number(this.v1.length),
            width: Number(this.v1.width),
            label: this.v1.label,
            color: 'blue',
          },
          {
            x: Number(this.v2.x),
            y: Number(this.v2.y),
            heading: Number(this.v2.heading),
            length: Number(this.v2.length),
            width: Number(this.v2.width),
            label: this.v2.label,
            color: 'red',
          },
        ],
        title: 'Crash Scene',
        show_grid: true,
      };

      if (this.impactX !== '' && this.impactY !== '') {
        payload.impact_point = {
          x: Number(this.impactX),
          y: Number(this.impactY),
        };
      }

      return payload;
    },

    async generate() {
      this.loading = true;
      this.error = null;

      try {
        const resp = await fetch('/api/v1/simulate/visualize', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.buildPayload()),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Request failed with status ${resp.status}`);
        }

        const data = await resp.json();
        const chartDiv = document.getElementById('scene-chart');
        if (chartDiv && data.plotly_json) {
          Plotly.newPlot(chartDiv, data.plotly_json.data, data.plotly_json.layout, {
            responsive: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
          });
        }
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
      } finally {
        this.loading = false;
      }
    },

    reset() {
      this.v1 = { x: 0, y: 0, heading: 0, length: 15, width: 6, label: 'Vehicle 1' };
      this.v2 = { x: 20, y: 10, heading: 90, length: 15, width: 6, label: 'Vehicle 2' };
      this.impactX = '';
      this.impactY = '';
      this.loading = false;
      this.error = null;

      const chartDiv = document.getElementById('scene-chart');
      if (chartDiv) {
        Plotly.purge(chartDiv);
      }
    },
  };
}
