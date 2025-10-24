document.addEventListener('DOMContentLoaded', async () => {

  if (!window.BASE) throw new Error('window.BASE is not defined');

  // Import modules once
  const authModule = await import(`${window.BASE}static/utils/js/services/authFetchService.js`);
  const apiModule = await import(`${window.BASE}static/utils/js/apiEndpoints.js`);

  const fetchWithAutoRefresh = authModule.fetchWithAutoRefresh;
  const API_ENDPOINTS = apiModule.API_ENDPOINTS;

  fetchWithAutoRefresh(API_ENDPOINTS.ORDER_COUNTS_SUMMARY)
    .then(res => {
      if (!res.ok) throw new Error('Failed to fetch summary');
      return res.json();
    })
    .then(data => {
      const container = document.getElementById('order-summary');
      container.innerHTML = `
        <div class="col-lg-4 col-12 mb-3">
          <div class="custom-box box-today">
            <div class="inner">
              <h3>${data.orders_today}</h3>
              <p>Orders Today</p>
            </div>
            <div class="icon">
              <i class="fas fa-calendar-day"></i>
            </div>
          </div>
        </div>
        <div class="col-lg-4 col-12 mb-3">
          <div class="custom-box box-week">
            <div class="inner">
              <h3>${data.orders_this_week}</h3>
              <p>Orders This Week</p>
            </div>
            <div class="icon">
              <i class="fas fa-chart-line"></i>
            </div>
          </div>
        </div>
        <div class="col-lg-4 col-12 mb-3">
          <div class="custom-box box-month">
            <div class="inner">
              <h3>${data.orders_this_month}</h3>
              <p>Orders This Month</p>
            </div>
            <div class="icon">
              <i class="fas fa-calendar-alt"></i>
            </div>
          </div>
        </div>
      `;
    })
    .catch(err => {
      console.error('Error loading order summary:', err);
      document.getElementById('order-summary').innerHTML = `
        <div class="col-12">
          <div class="alert alert-danger">Failed to load order summary.</div>
        </div>
      `;
    });
});
