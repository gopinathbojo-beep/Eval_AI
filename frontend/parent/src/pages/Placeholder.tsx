import { Empty, PageHeader } from "../components/ui";

/** A planned screen whose backend is not built yet. */
export default function Placeholder({ title, sub, what }: { title: string; sub?: string; what: string }) {
  return (
    <>
      <PageHeader title={title} sub={sub} />
      <Empty title="Coming soon" hint={what} />
    </>
  );
}
