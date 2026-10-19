import { useState } from "react";

function ProductCard({ product, onAdd }) {
  const [qty, setQty] = useState(1);
  const out = product.inventory <= 0;
  return (
    <div className={`card ${out ? "muted" : ""}`}>
      <div className="card-title">{product.name}</div>
      <div className="price">${product.price_display}</div>
      <div className={`stock ${product.inventory <= 5 ? "low" : ""}`}>
        {out ? "Out of stock" : `${product.inventory} in stock`}
      </div>
      <div className="row">
        <input
          type="number"
          min="1"
          max={product.inventory}
          value={qty}
          disabled={out}
          onChange={(e) => setQty(Math.max(1, Number(e.target.value)))}
        />
        <button disabled={out} onClick={() => onAdd(product.id, qty)}>
          Add
        </button>
      </div>
    </div>
  );
}

export default function Products({ products, onAdd }) {
  return (
    <section>
      <h2>Products</h2>
      <div className="grid">
        {products.map((p) => (
          <ProductCard key={p.id} product={p} onAdd={onAdd} />
        ))}
      </div>
    </section>
  );
}
