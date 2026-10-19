import { useState } from "react";

export default function Cart({ cart, onUpdate, onRemove, onCheckout }) {
  const [coupon, setCoupon] = useState("");

  if (!cart || cart.items.length === 0) {
    return (
      <section>
        <h2>Your Cart</h2>
        <p className="empty">Your cart is empty. Add something from the Shop tab.</p>
      </section>
    );
  }

  return (
    <section>
      <h2>Your Cart</h2>
      <table className="cart-table">
        <thead>
          <tr>
            <th>Product</th>
            <th>Unit</th>
            <th>Qty</th>
            <th>Line total</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {cart.items.map((i) => (
            <tr key={i.product_id}>
              <td>{i.name}</td>
              <td>${i.unit_price_display}</td>
              <td>
                <input
                  type="number"
                  min="1"
                  value={i.quantity}
                  onChange={(e) =>
                    onUpdate(i.product_id, Math.max(1, Number(e.target.value)))
                  }
                />
              </td>
              <td>${i.line_total_display}</td>
              <td>
                <button className="link" onClick={() => onRemove(i.product_id)}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="cart-footer">
        <div className="subtotal">
          Subtotal: <strong>${cart.subtotal_display}</strong>
        </div>
        <div className="checkout-row">
          <input
            placeholder="Coupon code (optional)"
            value={coupon}
            onChange={(e) => setCoupon(e.target.value)}
          />
          <button className="primary" onClick={() => onCheckout(coupon.trim())}>
            Checkout
          </button>
        </div>
      </div>
    </section>
  );
}
