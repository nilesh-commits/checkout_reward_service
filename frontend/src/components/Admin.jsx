import { useEffect, useState } from "react";
import { api } from "../api.js";

export default function Admin({ notify }) {
  const [report, setReport] = useState(null);
  const [lastCoupon, setLastCoupon] = useState(null);

  const load = async () => {
    try {
      setReport(await api.report());
    } catch (e) {
      notify(`${e.code || "ERROR"}: ${e.message}`);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const generate = async () => {
    try {
      const c = await api.generateCoupon();
      setLastCoupon(c);
      notify(`Coupon ${c.code} (${c.percent_off}% off) generated`, "success");
      await load();
    } catch (e) {
      notify(`${e.code || "ERROR"}: ${e.message}`);
    }
  };

  return (
    <section>
      <h2>Admin</h2>

      <div className="admin-actions">
        <button className="primary" onClick={generate}>
          Generate coupon at eligible milestone
        </button>
        <button onClick={load}>Refresh report</button>
      </div>

      {lastCoupon && (
        <div className="coupon-banner">
          Latest coupon: <code>{lastCoupon.code}</code> — {lastCoupon.percent_off}% off
          (milestone {lastCoupon.milestone})
        </div>
      )}

      {report && (
        <div className="report">
          <div className="stat-row">
            <Stat label="Total orders" value={report.total_orders} />
            <Stat label="Gross revenue" value={`$${report.gross_revenue_display}`} />
            <Stat label="Discounts" value={`$${(report.total_discounts_cents / 100).toFixed(2)}`} />
            <Stat label="Net revenue" value={`$${report.net_revenue_display}`} />
          </div>
          <div className="stat-row">
            <Stat label="Coupons generated" value={report.coupons_generated} />
            <Stat label="Coupons available" value={report.coupons_available} />
            <Stat label="Coupons redeemed" value={report.coupons_redeemed} />
          </div>

          <h3>Quantity sold by product</h3>
          <table className="cart-table">
            <thead>
              <tr>
                <th>Product</th>
                <th>Quantity</th>
              </tr>
            </thead>
            <tbody>
              {report.purchased_quantity_by_product.map((p) => (
                <tr key={p.product_id}>
                  <td>{p.product_name}</td>
                  <td>{p.quantity}</td>
                </tr>
              ))}
              {report.purchased_quantity_by_product.length === 0 && (
                <tr>
                  <td colSpan="2" className="empty">
                    No sales yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function Stat({ label, value }) {
  return (
    <div className="stat">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}
