import { useState } from "react";
import { api, downloadFile } from "../../api/client";
import { useApi } from "../../hooks/useApi";
import { Button, Card, Empty, ErrorPanel, Loading, PageHeader, Stat, StatusBadge } from "../../components/ui";
import { useToast } from "../../components/Toast";
import { date } from "../../utils/format";

interface LedgerRow { id: string; type: string; amount: number; balance_after: number; note: string | null; created_at: string }
interface Wallet { balance: number; held: number; can_buy: boolean; eval_per_sheet: number; low: boolean; ledger: LedgerRow[] }
interface Pack { id: string; name: string; credits: number; price_inr: number }
interface Payment { id: string; credits: number; amount_inr: number; status: string; invoice_no: string | null; created_at: string }
interface Order { order_id: string; payment_id: string; amount_paise: number; key_id: string | null; simulation: boolean }

declare global { interface Window { Razorpay?: new (o: Record<string, unknown>) => { open(): void } } }

const inr = (n: number) => `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;

function loadRazorpay(): Promise<void> {
  if (window.Razorpay) return Promise.resolve();
  return new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => ok();
    s.onerror = () => fail(new Error("The payment window could not be loaded. Check your connection."));
    document.body.appendChild(s);
  });
}

/** The school's credit wallet: balance, buying a pack (Razorpay, or simulated when no keys are set), history and invoices. */
export default function Credits() {
  const { data, error, loading, reload } = useApi<Wallet>("/credits");
  const packs = useApi<Pack[]>("/public/credit-packs");
  const payments = useApi<Payment[]>("/credits/payments");
  const toast = useToast();
  const [buying, setBuying] = useState<string | null>(null);

  const verify = async (order_id: string, payment_id: string, signature: string) => {
    await api("/credits/verify", { method: "POST", json: { order_id, payment_id, signature } });
    toast("Credits added", "ok");
    await Promise.all([reload(), payments.reload()]);
  };

  const buy = async (p: Pack) => {
    setBuying(p.id);
    try {
      const o = await api<Order>("/credits/order", { method: "POST", json: { pack_id: p.id } });
      if (o.simulation) {
        await verify(o.order_id, `pay_sim_${o.payment_id.slice(0, 8)}`, "simulated");
      } else {
        await loadRazorpay();
        new window.Razorpay!({
          key: o.key_id, order_id: o.order_id, amount: o.amount_paise, currency: "INR", name: "ADEM", description: p.name,
          handler: (r: { razorpay_order_id: string; razorpay_payment_id: string; razorpay_signature: string }) =>
            verify(r.razorpay_order_id, r.razorpay_payment_id, r.razorpay_signature).catch((e) => toast(e.message, "mark")),
        }).open();
      }
    } catch (e) { toast((e as Error).message, "mark"); }
    finally { setBuying(null); }
  };

  if (loading && !data) return <Loading />;
  if (error) return <ErrorPanel error={error} />;
  if (!data) return null;
  return (
    <>
      <PageHeader title="Credits" sub={`Grading one answer sheet uses ${data.eval_per_sheet} credit(s). Grading the same sheet again is free.`} />
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3">
        <Stat label="Balance" value={data.balance} tone={data.low ? "mark" : "ok"} hint={data.low ? "Running low" : undefined} />
        <Stat label="Held for running evaluations" value={data.held} />
      </div>

      {data.can_buy && (
        <Card className="mt-6">
          <h2 className="mb-3 font-display text-lg font-semibold">Buy credits</h2>
          {packs.data?.length ? (
            <div className="grid gap-3 sm:grid-cols-3">
              {packs.data.map((p) => (
                <div key={p.id} className="rounded-lg border border-line p-4">
                  <p className="font-semibold">{p.name}</p>
                  <p className="mt-1 text-2xl font-display">{p.credits} <span className="text-sm text-mute">credits</span></p>
                  <p className="text-sm text-mute">{inr(p.price_inr)} incl. GST</p>
                  <Button className="mt-3 w-full" variant="primary" busy={buying === p.id} disabled={!!buying} onClick={() => buy(p)}>Buy</Button>
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-mute">No credit packs are on sale right now.</p>}
        </Card>
      )}

      <h2 className="mb-3 mt-8 font-display text-lg font-semibold">History</h2>
      {data.ledger.length ? (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-sunken/60 text-left text-xs uppercase text-mute">
              <tr><th className="px-3 py-2">When</th><th className="px-3 py-2">What</th><th className="px-3 py-2">Credits</th><th className="px-3 py-2">Balance</th></tr>
            </thead>
            <tbody>
              {data.ledger.map((r) => (
                <tr key={r.id} className="border-t border-line">
                  <td className="px-3 py-2">{date(r.created_at)}</td>
                  <td className="px-3 py-2">{r.note || <StatusBadge status={r.type} />}</td>
                  <td className={`px-3 py-2 ${r.amount < 0 ? "text-mark" : "text-ok"}`}>{r.amount > 0 ? "+" : ""}{r.amount}</td>
                  <td className="px-3 py-2">{r.balance_after}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <Empty title="No credit movements yet" />}

      {!!payments.data?.length && (
        <>
          <h2 className="mb-3 mt-8 font-display text-lg font-semibold">Payments and invoices</h2>
          <ul className="space-y-2">
            {payments.data.map((p) => (
              <li key={p.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-sm">
                <span>{date(p.created_at)} · {p.credits} credits · {inr(p.amount_inr)}</span>
                <span className="flex items-center gap-2">
                  <StatusBadge status={p.status} />
                  {p.invoice_no && <Button small variant="ghost" onClick={() =>
                    downloadFile(`/credits/invoices/${p.id}`, `${p.invoice_no}.pdf`).catch((e) => toast(e.message, "mark"))}>Invoice</Button>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
