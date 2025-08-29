document.addEventListener("DOMContentLoaded", function () {
    const urlParams = new URLSearchParams(window.location.search);
    const vendorId = urlParams.get('vendor_id');

    // Clean the URL by removing the query parameters
    window.history.replaceState({}, document.title, window.location.pathname);
    const notifyBtn = document.getElementById('notifyButton');
    notifyBtn.addEventListener('click', function () {
        AppUtils.playNotificationSound();
        });
    const orderSlotIds = [
        'left-col-1',
        'left-col-2',
        'right-col-1',
        'right-col-2',
        'right-col-3',
        'right-col-4',
        'right-col-5',
        'right-col-6'
    ];

    let lastShownOrderIds = new Set(); // Store previously shown order IDs

    function fetchAndDisplayRecentOrders() {
        fetch(`/api/get_recent_orders/?vendor_id=${vendorId}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error("Failed to fetch orders");
                }
                return response.json();
            })
            .then(data => {
                // Clear previous content
                orderSlotIds.forEach(id => {
                    const slot = document.getElementById(id);
                    if (slot) slot.innerHTML = '';
                });
    
                const newReadyOrders = data
                    .filter(order => order.status === 'ready')
                    .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
                    .slice(0, 8);
    
                const displayedOrderIds = [];
    
                let hasNewOrder = false; // Flag to detect new entries
    
                newReadyOrders.forEach((order, index) => {
                    const slotId = orderSlotIds[index];
                    const slotEl = document.getElementById(slotId);
    
                    if (slotEl) {
                        const orderHTML = `
                            <div class="order-card" style="animation-delay: ${index * 0.05}s">
                                <div class="order-number">${order.token_no}</div>
                                <div class="order-details" style="display: none;">
                                    <p class="mb-1">Vendor: ${order.vendor || 'N/A'}</p>
                                    <small>Ready at: ${new Date(order.updated_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</small>
                                </div>
                            </div>
                        `;
                        slotEl.innerHTML = orderHTML;
                        displayedOrderIds.push(order.id);
    
                        if (!lastShownOrderIds.has(order.id)) {
                            hasNewOrder = true; // Found at least one new
                        }
                    }
                });
    
                // Hide unused slots
                for (let i = newReadyOrders.length; i < orderSlotIds.length; i++) {
                    const slot = document.getElementById(orderSlotIds[i]);
                    if (slot) slot.innerHTML = '';
                }
    
                // 🔔 Only play sound if there's at least one new unseen order
                if (hasNewOrder) {
                    AppUtils.playNotificationSound();
                }
    
                // Update memory with current shown order IDs
                lastShownOrderIds = new Set(displayedOrderIds);
            })
            .catch(error => {
                console.error("Error fetching recent orders:", error);
            });
    }
    

    // Enhanced auto-refresh with error handling
    let refreshInterval = setInterval(() => {
        try {
            fetchAndDisplayRecentOrders();
            // AppUtils.playNotificationSound();
        } catch (e) {
            console.error("Error in refresh cycle:", e);
        }
    }, 1000);
    
    // Initial load with error handling
    try {
        fetchAndDisplayRecentOrders();
    } catch (e) {
        console.error("Initial load failed:", e);
    }

    // Clean up interval when page unloads
    window.addEventListener('beforeunload', () => {
        clearInterval(refreshInterval);
    });
});