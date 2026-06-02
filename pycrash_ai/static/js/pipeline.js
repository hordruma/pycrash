function pipelineApp() {
  return {
    // Input
    text: '',
    file: null,
    provider: '',
    apiKey: '',
    model: '',
    cor: 0.15,
    tstop: 0.5,
    autoSimulate: true,

    // State
    loading: false,
    step: '',
    error: null,

    // Results
    extraction: null,
    vehicleSpecs: null,
    simulation: null,
    summary: null,
    caseId: null,
    graph: null,

    _buildHeaders() {
      const headers = {};
      if (this.provider) headers['X-Provider'] = this.provider;
      if (this.apiKey) headers['X-Api-Key'] = this.apiKey;
      if (this.model) headers['X-Model'] = this.model;
      return headers;
    },

    async analyzeText() {
      if (!this.text.trim()) {
        this.error = 'Please enter a crash report or description to analyze.';
        return;
      }

      this.loading = true;
      this.error = null;
      this.step = 'extracting';
      this._clearResults();

      try {
        const resp = await fetch('/api/v1/pipeline', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...this._buildHeaders(),
          },
          body: JSON.stringify({
            text: this.text,
            auto_simulate: this.autoSimulate,
            cor: Number(this.cor),
            tstop: Number(this.tstop),
          }),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Pipeline failed (${resp.status})`);
        }

        this.step = 'simulating';
        const data = await resp.json();

        this.extraction = data.extraction || null;
        this.vehicleSpecs = data.vehicle_specs || null;
        this.simulation = data.simulation || null;
        this.summary = data.summary || null;
        this.caseId = data.case_id || null;
        this.graph = data.graph || null;
        this.step = 'complete';
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
        this.step = '';
      } finally {
        this.loading = false;
      }
    },

    handleFile(event) {
      const files = event.target.files;
      this.file = files && files.length > 0 ? files[0] : null;
    },

    async uploadFile() {
      if (!this.file) {
        this.error = 'Please select a file to upload.';
        return;
      }

      this.loading = true;
      this.error = null;
      this.step = 'extracting';
      this._clearResults();

      try {
        const formData = new FormData();
        formData.append('file', this.file);

        const resp = await fetch('/api/v1/extract/upload', {
          method: 'POST',
          headers: this._buildHeaders(),
          body: formData,
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Upload failed (${resp.status})`);
        }

        const data = await resp.json();
        this.extraction = data;
        this.step = 'complete';
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
        this.step = '';
      } finally {
        this.loading = false;
      }
    },

    _clearResults() {
      this.extraction = null;
      this.vehicleSpecs = null;
      this.simulation = null;
      this.summary = null;
      this.caseId = null;
      this.graph = null;
    },

    reset() {
      this.text = '';
      this.file = null;
      this.provider = '';
      this.apiKey = '';
      this.model = '';
      this.cor = 0.15;
      this.tstop = 0.5;
      this.autoSimulate = true;
      this.loading = false;
      this.step = '';
      this.error = null;
      this._clearResults();

      // Reset file input element if present
      const fileInput = document.querySelector('input[type="file"]');
      if (fileInput) fileInput.value = '';
    },

    goToCase() {
      if (this.caseId) {
        window.dispatchEvent(new CustomEvent('navigate', {
          detail: { page: 'cases', caseId: this.caseId },
        }));
      }
    },

    goToSimulator(specs) {
      window.dispatchEvent(new CustomEvent('navigate', {
        detail: { page: 'simulator', vehicleSpecs: specs || this.vehicleSpecs },
      }));
    },

    // Display helpers

    confidenceColor(confidence) {
      if (confidence >= 0.8) return 'text-green-600';
      if (confidence >= 0.5) return 'text-yellow-600';
      return 'text-red-600';
    },

    confidenceLabel(confidence) {
      if (confidence >= 0.8) return 'High';
      if (confidence >= 0.5) return 'Medium';
      return 'Low';
    },

    formatSpeed(mph) {
      if (mph === null || mph === undefined) return 'Unknown';
      return mph + ' mph';
    },
  };
}
