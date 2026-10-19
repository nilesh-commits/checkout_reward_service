import { useCallback, useEffect, useState } from "react";
import { api } from "./api.js";
import Products from "./components/Products.jsx";
import Cart from "./components/Cart.jsx";
import Order from "./components/Order.jsx";
import Admin from "./components/Admin.jsx";
import Toast from "./components/Toast.jsx";

const CART_KEY = "uniblox.cartId";

export default function App() {
  const [tab, setTab] = useState("shop");
  const [products, setProducts] = useState([]);
  const [cartId, setCartId] = useState(() => localStorage.getItem(CART_KEY));
  const [cart, setCart] = useState(null);
  const [lastOrder, setLastOrder] = useState(null);
  const [toast, setToast] = useState(null);

  const notify = useCallback((message, kind = "error") => {
    setToast({ message, kind });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const refreshProducts = useCallback(async () => {
    try {
      setProducts(await api.listProducts());
    } catch (e) {
      notify(e.message);
    }
  }, [notify]);

  const refreshCart = useCallback(
    async (id = cartId) => {
      if (!id) return;
      try {
        setCart(await api.getCart(id));
      } catch (e) {
        // Cart vanished (e.g. fresh DB) — forget it.
        localStorage.removeItem(CART_KEY);
        setCartId(null);
        setCart(null);
      }
    },
    [cartId]
  );

  useEffect(() => {
    refreshProducts();
  }, [refreshProducts]);

  useEffect(() => {
    refreshCart();
  }, [refreshCart]);

  const ensureCart = useCallback(async () => {
    if (cartId) return cartId;
    const c = await api.createCart();
    localStorage.setItem(CART_KEY, c.id);
    setCartId(String(c.id));
    setCart(c);
    return c.id;
  }, [cartId]);

  const addToCart = async (productId, qty) => {
    try {
      const id = await ensureCart();
      const updated = await api.addItem(id, productId, qty);
      setCart(updated);
      notify("Added to cart", "success");
    } catch (e) {
      notify(`${e.code || "ERROR"}: ${e.message}`);
    }
  };

  const onCheckout = async (couponCode) => {
    try {
      const order = await api.checkout(cartId, couponCode);
      setLastOrder(order);
      localStorage.removeItem(CART_KEY);
      setCartId(null);
      setCart(null);
      await refreshProducts();
      setTab("order");
      notify(`Order #${order.id} placed`, "success");
    } catch (e) {
      notify(`${e.code || "ERROR"}: ${e.message}`);
    }
  };

  const itemCount = cart?.items?.reduce((n, i) => n + i.quantity, 0) || 0;

  return (
    <div className="app">
      <header>
        <div className="brand">🛒 Checkout &amp; Rewards</div>
        <nav>
          <button className={tab === "shop" ? "active" : ""} onClick={() => setTab("shop")}>
            Shop
          </button>
          <button className={tab === "cart" ? "active" : ""} onClick={() => setTab("cart")}>
            Cart{itemCount > 0 ? ` (${itemCount})` : ""}
          </button>
          <button className={tab === "order" ? "active" : ""} onClick={() => setTab("order")}>
            Order
          </button>
          <button className={tab === "admin" ? "active" : ""} onClick={() => setTab("admin")}>
            Admin
          </button>
        </nav>
      </header>

      <main>
        {tab === "shop" && <Products products={products} onAdd={addToCart} />}
        {tab === "cart" && (
          <Cart
            cart={cart}
            onUpdate={async (pid, qty) => {
              try {
                setCart(await api.updateItem(cartId, pid, qty));
              } catch (e) {
                notify(`${e.code}: ${e.message}`);
              }
            }}
            onRemove={async (pid) => {
              try {
                setCart(await api.removeItem(cartId, pid));
              } catch (e) {
                notify(`${e.code}: ${e.message}`);
              }
            }}
            onCheckout={onCheckout}
          />
        )}
        {tab === "order" && <Order order={lastOrder} />}
        {tab === "admin" && <Admin notify={notify} />}
      </main>

      {toast && <Toast {...toast} />}
    </div>
  );
}
