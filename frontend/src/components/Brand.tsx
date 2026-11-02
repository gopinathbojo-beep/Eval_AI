import logoIcon from "../assets/logo-icon.png";

/** Logo icon: a blue tick badge with an orange star. */
export function BrandMark({ className = "" }: { className?: string }) {
  return <img src={logoIcon} alt="" aria-hidden className={`object-contain ${className}`} />;
}

/** Icon, "Eval AI" and tagline. The text is real text, so it stays crisp at any size; `onDark` makes it light
 * for the dark sidebar and login cover. */
export function BrandLabel({ size = "md", onDark = true }: { size?: "md" | "lg"; onDark?: boolean }) {
  const lg = size === "lg";
  return (
    <span className="inline-flex items-center gap-2.5">
      <BrandMark className={lg ? "h-12 w-12" : "h-10 w-10"} />
      <span className="flex flex-col leading-none">
        <span className={`font-semibold tracking-tight ${lg ? "text-3xl" : "text-2xl"} ${onDark ? "text-white" : "text-ink"}`}>
          Eval AI
        </span>
        <span
          className={`mt-1 whitespace-nowrap font-medium uppercase ${lg ? "text-[10px] tracking-[0.22em]" : "text-[8.5px] tracking-[0.18em]"} ${
            onDark ? "text-white/60" : "text-mute"
          }`}
        >
          Assess · Measure · Improve
        </span>
      </span>
    </span>
  );
}
