export default function Order({ order }) {
  if (!order) {
    return (
      <section>
        <h2>Order</h2>
        <p className="empty">No recent order. Check out a cart to see it here.</p>
      </section>
    );
  }

  return (
    <section>
      <h2>Order #{order.id}</h2>
      <p className="confirm">✓ Order placed successfully</p>
      <table className="cart-table">
        <thead>
          <tr>
            <th>Product</th>
            <th>Unit (at purchase)</th>
            <th>Qty</th>
            <th>Line total</th>
          </tr>
        </thead>
        <tbody>
          {order.items.map((i) => (
            <tr key={i.product_id}>
              <td>{i.product_name}</td>
              <td>${(i.unit_price_cents / 100).toFixed(2)}</td>
              <td>{i.quantity}</td>
              <td>${i.line_total_display}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="totals">
        <div>
          Subtotal: <span>${order.subtotal_display}</span>
        </div>
        {order.coupon_code && (
          <div className="discount">
            Discount ({order.coupon_code}): <span>-${order.discount_display}</span>
          </div>
        )}
        <div className="grand">
          Total: <strong>${order.total_display}</strong>
        </div>
      </div>
    </section>
  );
}
