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
 */
export const STATUS_MESSAGE_MAP = {
  preparing: (data) => `
    Your Order <strong>${data.token_no}</strong> for <strong>${data.name}</strong>
    is now <strong>preparing</strong>. Please wait while we finish it.`,

  ready: (data) => `
    Your Order <strong>${data.token_no}</strong> for <strong>${data.name}</strong>
    is now <strong>ready</strong> at <strong>Counter ${data.counter_no}</strong>.`,

  cancelled: (data) => `
    Unfortunately, your order <strong>${data.token_no}</strong> for <strong>${data.name}</strong> 
    has been cancelled. Please contact staff for assistance.`,

  delivered: (data) => `
    Your Order <strong>${data.token_no}</strong> for <strong>${data.name}</strong>
    has been delivered. Thank you for choosing us!`,

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
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.name}</strong>
    is now <strong>waiting</strong> for allocation.`,
  
  allocated: (data) => `
    Your Booking No <strong>${data.booking_no}</strong> for <strong>${data.name}</strong>
    has been Allocated at <strong>${data.utility_name}</strong>.`,
  
  operation_closed: (data) => `
    Thank you for choosing us today.`,
  
};
