function casesApp() {
  return {
    cases: [],
    selectedCase: null,
    activeTab: 'entity',
    newCase: { title: '' },
    loading: false,
    error: null,
    timeline: null,
    layers: null,

    layerTabs: [
      { key: 'entity', label: 'Entity' },
      { key: 'temporal', label: 'Temporal' },
      { key: 'spatial', label: 'Spatial' },
      { key: 'evidence', label: 'Evidence' },
      { key: 'causal', label: 'Causal' },
      { key: 'physical', label: 'Physical' },
    ],

    async loadCases() {
      this.loading = true;
      this.error = null;

      try {
        const resp = await fetch('/api/v1/cases');
        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Failed to load cases (${resp.status})`);
        }

        const caseIds = await resp.json();
        // The list endpoint returns case IDs; fetch details for each
        this.cases = caseIds.map((id) => ({ case_id: id }));
      } catch (err) {
        this.error = err.message || 'Failed to load cases';
      } finally {
        this.loading = false;
      }
    },

    async viewCase(caseId) {
      this.loading = true;
      this.error = null;
      this.selectedCase = null;
      this.timeline = null;
      this.layers = null;
      this.activeTab = 'entity';

      try {
        const resp = await fetch(`/api/v1/cases/${encodeURIComponent(caseId)}/export`);
        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Failed to load case (${resp.status})`);
        }

        this.selectedCase = await resp.json();

        // Load layers and timeline in parallel
        await Promise.all([
          this.loadLayers(caseId),
          this.loadTimeline(caseId),
        ]);
      } catch (err) {
        this.error = err.message || 'Failed to load case details';
      } finally {
        this.loading = false;
      }
    },

    async createCase() {
      if (!this.newCase.title.trim()) {
        this.error = 'Please enter a case title';
        return;
      }

      this.loading = true;
      this.error = null;

      try {
        const caseId = 'case_' + Date.now().toString(36);
        const resp = await fetch('/api/v1/cases', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_id: caseId,
            title: this.newCase.title.trim(),
          }),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Failed to create case (${resp.status})`);
        }

        this.newCase.title = '';
        await this.loadCases();
      } catch (err) {
        this.error = err.message || 'Failed to create case';
      } finally {
        this.loading = false;
      }
    },

    async deleteCase(caseId) {
      if (!confirm(`Delete case "${caseId}"? This cannot be undone.`)) return;

      this.loading = true;
      this.error = null;

      try {
        const resp = await fetch(`/api/v1/cases/${encodeURIComponent(caseId)}`, {
          method: 'DELETE',
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Failed to delete case (${resp.status})`);
        }

        await this.loadCases();
      } catch (err) {
        this.error = err.message || 'Failed to delete case';
      } finally {
        this.loading = false;
      }
    },

    async loadTimeline(caseId) {
      try {
        const resp = await fetch(`/api/v1/cases/${encodeURIComponent(caseId)}/timeline/full`);
        if (resp.ok) {
          this.timeline = await resp.json();
        }
      } catch (_) {
        // Timeline is supplementary; don't block on failure
      }
    },

    async loadLayers(caseId) {
      try {
        const resp = await fetch(`/api/v1/cases/${encodeURIComponent(caseId)}/layers`);
        if (resp.ok) {
          this.layers = await resp.json();
        }
      } catch (_) {
        // Layers summary is supplementary
      }
    },

    getLayerNodes(layer) {
      if (!this.selectedCase) return [];

      const nodes = this.selectedCase.nodes || [];
      // Filter nodes by layer label
      const layerMap = {
        entity: ['Vehicle', 'Driver', 'Object', 'Scene'],
        temporal: ['Event', 'Phase'],
        spatial: ['Position', 'ImpactPoint', 'Trajectory'],
        evidence: ['Evidence', 'Source', 'Contradiction', 'Gap'],
        causal: ['Factor', 'CausalChain'],
        physical: ['DeltaV', 'Force', 'Crush', 'Energy'],
      };

      const labels = layerMap[layer] || [];
      return nodes.filter((n) => {
        const nodeLabel = n.label || n.type || '';
        return labels.some((l) => nodeLabel.toLowerCase().includes(l.toLowerCase()));
      });
    },

    formatNodeProperties(node) {
      // Return key properties for display, excluding internal IDs
      const skip = new Set(['id', 'label', 'type', '_id']);
      const props = {};
      for (const [key, value] of Object.entries(node)) {
        if (!skip.has(key) && value !== null && value !== undefined && value !== '') {
          props[key] = value;
        }
      }
      return props;
    },

    back() {
      this.selectedCase = null;
      this.timeline = null;
      this.layers = null;
      this.activeTab = 'entity';
      this.error = null;
    },
  };
}
