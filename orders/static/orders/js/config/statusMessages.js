// orders/static/orders/js/config/statusMessages.js

/**
 * Centralized message templates for notification modal.
 * 
 * Each key in STATUS_MESSAGE_MAP corresponds to a backend status.
 * The function receives `pushData` (order/flight info) and returns an HTML string.
 *
 * Example:
 *   STATUS_MESSAGE_MAP['ready'](pushData)
 *     → "Your Order 12 for Café Rio is now ready at Counter 3."
 *
 * NOTE: Keep these templates generic and concise to ensure they are safe for all
 * project variants (Food Flash, Airline Flash, Dine Flash, etc.). 
 * Flavour-specific overrides should be handled in notificationService.js.
 */
export const STATUS_MESSAGE_MAP = {
  preparing: (data) => `
    Your Order <strong>${data.token_no}</strong> for <strong>${data.item_name || data.name || 'your item'}</strong>
    is now <strong>preparing</strong>. Please wait while we finish it.`,
  item_preparing: (data) => STATUS_MESSAGE_MAP.preparing(data),
  buffet_item_preparing: (data) => STATUS_MESSAGE_MAP.preparing(data),

  ready: (data) => `
    Your order <strong>${data.token_no}</strong> is <strong>ready</strong>.`,
  item_ready: (data) => STATUS_MESSAGE_MAP.ready(data),
  buffet_item_ready: (data) => STATUS_MESSAGE_MAP.ready(data),

  buffet_utilities_ready: (data) => STATUS_MESSAGE_MAP.buffet_utilities_status(data),

  buffet_utilities_status: (data) => {
    let blocks = Array.isArray(data.utilities) ? data.utilities : [];
    if (!blocks.length && Array.isArray(data.ready_utilities)) {
      blocks = data.ready_utilities.map((x) => ({
        name: x.name,
        lines: [{ status: "ready", quantity: 1 }],
      }));
    }
    const parts = blocks.map((b) => {
      const name = (b && b.name) || "Station";
      const bits = (Array.isArray(b.lines) ? b.lines : []).map((ln) => {
        const st = ln.status || "?";
        const qty = ln.quantity != null ? Number(ln.quantity) : 1;
        const q = Number.isFinite(qty) && qty !== 1 ? ` ×${qty}` : "";
        return `${st}${q}`;
      });
      return `<strong>${name}</strong> (${bits.join(", ") || "—"})`;
    });
    return `
    Update for order <strong>${data.token_no}</strong>:<br>
    ${parts.join("<br>")}`;
  },

  cancelled: (data) => `
    Unfortunately, your order <strong>${data.token_no}</strong> for <strong>${data.item_name || data.name || 'your item'}</strong> 
    has been cancelled. Please contact staff for assistance.`,
  item_cancelled: (data) => STATUS_MESSAGE_MAP.cancelled(data),
  buffet_item_cancelled: (data) => STATUS_MESSAGE_MAP.cancelled(data),


  delivered: (data) => `
    Your Order <strong>${data.token_no}</strong> for <strong>${data.item_name || data.name || 'your item'}</strong>
    has been delivered. Thank you for choosing us!`,
  item_delivered: (data) => STATUS_MESSAGE_MAP.delivered(data),
  order_delivered: (data) => STATUS_MESSAGE_MAP.delivered(data),
  item_operation_closed: (data) => `
    Your order <strong>${data.token_no}</strong> for <strong>${data.item_name || data.name || "this station"}</strong>:
    this service is <strong>closed</strong> for now. Thank you for choosing us today.`,

  buffetstatus: (data) => `
    Your order has been received, token no : <strong>${data.token_no}</strong>`,



  checked_in: (data) => `
    You have successfully checked-In for <strong>Flight ${data.flight_no}</strong>.`,

  boarding_shortly: (data) => `
    <strong>Flight ${data.flight_no}</strong> will be ready for boarding shortly. 
    Kindly wait for next announcement.`,

  boarding_announced: (data) => `
    <strong>Flight ${data.flight_no}</strong> is ready for boarding.
    Kindly proceed through boarding gate.`,

  rescheduled: (data) => `
    <strong>Flight ${data.flight_no}</strong> is Resheduled.
    Kindly contact the airline staff.`,

  gate_change: (data) => `
    Gate No changed.Revised Gate No will be Announced Shortly`,

  flightcancel: (data) => `
    Kindly contact the airline staff.`,

  waiting: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    is now <strong>waiting</strong> for allocation.`,

  allocated: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    has been Allocated at <strong>${data.utility_name}</strong>.`,

  utility_transfer: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    has been transferred to <strong>${data.utility_name}</strong>.`,

  occupied: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    is now <strong>Occupied</strong>. Enjoy your meal!`,

  booking_cancelled: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.alias_name || data.name || 'the outlet'}</strong>
    has been <strong>Cancelled</strong>.`,

  operation_closed: (data) => `
    Thank you for choosing us today.`,

  hospital_pre_announcement: (data) => {
    const dept = data.department_name || data.utility_name || "your department";
    const eta = data.eta_minutes != null ? data.eta_minutes : "-";
    const position = data.queue_position != null ? data.queue_position : "-";
    const booking = data.booking_no || data.token_no || "-";
    return `
    <strong>${dept}</strong>: your turn is approaching.<br>
    Token <strong>${booking}</strong> · queue position <strong>${position}</strong><br>
    Estimated wait: <strong>${eta} minute(s)</strong>.`;
  },

  buffet_pre_announcement: (data) => {
    const item = data.item_name || data.utility_name || "your item";
    const token = data.token_no != null ? data.token_no : "-";
    const distance = data.distance_from_ready != null ? data.distance_from_ready : "-";
    const eta = data.eta_minutes != null && Number(data.eta_minutes) > 0
      ? Number(data.eta_minutes)
      : null;
    if (eta != null) {
      return `
    Your Order <strong>${token}</strong> for <strong>${item}</strong> is approaching its turn
    (approximately <strong>${eta}</strong> minute(s) away).`;
    }
    return `
    Your Order <strong>${token}</strong> for <strong>${item}</strong> is approaching its turn
    (about <strong>${distance}</strong> ahead in the queue).`;
  },

};
