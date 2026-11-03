import { Card, PageHeader } from "../components/ui";
import { IconSparkles } from "../components/Icons";

/** Question paper and answer key generation: coming soon. */
export default function QpGeneration() {
  return (
    <div className="space-y-6">
      <PageHeader title="QP & answer key generation" sub="Generate CBSE question papers with matching answer keys." />
      <Card className="flex flex-col items-center px-6 py-16 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-pen-soft text-pen">
          <IconSparkles size={22} />
        </span>
        <h2 className="mt-4 text-lg font-semibold text-ink">Coming soon</h2>
        <p className="mt-1 max-w-md text-sm text-mute">
          You will be able to pick a class, subject and chapters and get a question paper with its answer key.
        </p>
      </Card>
    </div>
  );
}
