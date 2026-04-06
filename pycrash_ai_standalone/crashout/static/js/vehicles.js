function vehiclesApp() {
  return {
    year: '',
    make: '',
    model: '',
    makes: [],
    results: [],
    loading: false,
    error: null,

    async init() {
      await this.loadMakes();
    },

    async loadMakes() {
      try {
        const resp = await fetch('/api/v1/vehicles/makes');
        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Failed to load makes (${resp.status})`);
        }
        this.makes = await resp.json();
      } catch (err) {
        this.error = err.message || 'Failed to load vehicle makes';
      }
    },

    async search() {
      this.loading = true;
      this.error = null;
      this.results = [];

      try {
        const params = new URLSearchParams();
        if (this.year) params.set('year', this.year);
        if (this.make) params.set('make', this.make);
        if (this.model) params.set('model', this.model);

        const url = '/api/v1/vehicles/lookup' + (params.toString() ? '?' + params.toString() : '');
        const resp = await fetch(url);

        if (resp.status === 404) {
          this.results = [];
          return;
        }

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Search failed (${resp.status})`);
        }

        this.results = await resp.json();
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
      } finally {
        this.loading = false;
      }
    },

    selectVehicle(v) {
      // Store selected vehicle in a global for cross-component use
      window.__pycrash_selected_vehicle = v;
      window.dispatchEvent(new CustomEvent('vehicle-selected', { detail: v }));
    },
  };
}
