function reportsApp() {
  return {
    // Form
    simulationJobId: '',
    montecarloJobId: '',
    caseNumber: '',
    caseTitle: '',
    analystName: '',
    dateOfLoss: '',

    // State
    loading: false,
    error: null,

    // Result
    report: null,

    async generate() {
      if (!this.simulationJobId.trim()) {
        this.error = 'Simulation Job ID is required.';
        return;
      }

      this.loading = true;
      this.error = null;
      this.report = null;

      try {
        const payload = {
          simulation_job_id: this.simulationJobId.trim(),
          montecarlo_job_id: this.montecarloJobId.trim() || null,
          case_number: this.caseNumber.trim() || null,
          case_title: this.caseTitle.trim() || null,
          analyst_name: this.analystName.trim() || null,
          date_of_loss: this.dateOfLoss.trim() || null,
        };

        const resp = await fetch('/api/v1/report', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (!resp.ok) {
          const detail = await resp.json().catch(() => null);
          throw new Error(detail?.detail || `Request failed with status ${resp.status}`);
        }

        const data = await resp.json();
        this.report = {
          report_id: data.report_id,
          pdf_url: data.pdf_url,
          html_url: data.html_url || null,
        };
      } catch (err) {
        this.error = err.message || 'An unexpected error occurred';
      } finally {
        this.loading = false;
      }
    },

    reset() {
      this.simulationJobId = '';
      this.montecarloJobId = '';
      this.caseNumber = '';
      this.caseTitle = '';
      this.analystName = '';
      this.dateOfLoss = '';
      this.loading = false;
      this.error = null;
      this.report = null;
    },
  };
}
