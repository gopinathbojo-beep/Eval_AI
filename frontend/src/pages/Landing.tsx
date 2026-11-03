import { Link, Navigate } from "react-router-dom";
import { BrandLabel } from "../components/Brand";
import { ThemeToggle } from "../components/ThemeToggle";
import { useAuth } from "../context/Auth";
import { LinkButton, Loading } from "../components/ui";

export default function Landing() {
  const { teacher, loading } = useAuth();
  if (loading) return <Loading />;
  if (teacher)
    return (
      <Navigate
        to={
          teacher.is_admin
            ? "/admin"
            : teacher.profile_complete
                ? "/dashboard"
                : "/onboarding"
        }
        replace
      />
    );
  return (
    <main className="app-shell app-bg flex min-h-screen flex-col px-5 sm:px-10">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between gap-4 py-6">
        <BrandLabel onDark={false} />
        <ThemeToggle />
      </header>
      <section className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-center justify-center py-12 text-center sm:py-20">
        <p className="aurora-text text-xs font-semibold uppercase tracking-[0.2em]">
          For CBSE Classes 10 &amp; 12
        </p>
        <h1 className="aurora-text mt-5 font-display text-4xl font-semibold leading-tight sm:text-6xl">
          More insight.
          <br />
          Less time marking.
        </h1>
        <p className="mt-6 max-w-xl text-base leading-relaxed text-mute sm:text-lg">
          Eval AI evaluates handwritten answer sheets with your question paper and answer key, so schools and
          parents get fair marks, clear feedback and reports in a fraction of the time.
        </p>
        <LinkButton to="/login" variant="primary" className="mt-9 w-full max-w-xs px-8 py-3.5 text-base">
          Login
        </LinkButton>
        <p className="mt-4 text-sm text-mute">
          New to Eval AI?{" "}
          <Link to="/register" className="font-semibold text-pen underline-offset-2 hover:underline">
            Register here
          </Link>
        </p>
      </section>
    </main>
  );
}
