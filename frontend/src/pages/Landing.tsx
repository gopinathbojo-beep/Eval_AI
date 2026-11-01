import { Link, Navigate } from "react-router-dom";
import { BrandLabel } from "../components/Brand";
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
            : teacher.must_change_password
              ? "/account"
              : teacher.profile_complete
                ? "/dashboard"
                : "/onboarding"
        }
        replace
      />
    );
  return (
    <main className="desk min-h-screen px-5 sm:px-10">
      <header className="mx-auto flex max-w-6xl items-center justify-between gap-4 py-6">
        <BrandLabel onDark={false} />
        <nav aria-label="Account">
          <Link
            to="/login"
            className="mr-4 text-sm font-semibold text-pen hover:underline"
          >
            Login
          </Link>
          <LinkButton to="/register" variant="primary">
            Register
          </LinkButton>
        </nav>
      </header>
      <section className="mx-auto grid max-w-6xl items-center gap-14 py-16 sm:py-24 lg:grid-cols-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-pen">
            For CBSE Classes 10 &amp; 12
          </p>
          <h1 className="mt-5 font-display text-5xl font-semibold leading-tight sm:text-6xl">
            More insight.
            <br />
            Less time marking.
          </h1>
          <p className="mt-6 max-w-md text-lg leading-relaxed text-mute">
            Turn answer sheets into meaningful feedback. Evaluate with your
            question paper and marking scheme, review the results, and help
            every student see their next step.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <LinkButton to="/register" variant="primary" className="px-6 py-3">
              Get started — Register
            </LinkButton>
            <LinkButton to="/login" variant="outline" className="px-6 py-3">
              Login to your workspace
            </LinkButton>
          </div>
          <p className="mt-4 text-xs text-mute">
            For schools and parents. Teachers log in with their school
            credentials.
          </p>
        </div>
        <div className="rounded-2xl border border-line bg-surface p-6 shadow-card sm:p-9">
          <p className="text-xs font-semibold uppercase tracking-widest text-mute">
            Getting started feels like a conversation
          </p>
          <p className="mt-7 max-w-sm rounded-2xl rounded-tl-sm bg-sunken px-5 py-4 font-display text-xl">
            Hi! Who are you joining Eval AI as?
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Link
              to="/register"
              className="rounded-xl border border-line p-5 hover:border-pen"
            >
              <span className="block font-semibold text-pen">
                School management
              </span>
              <span className="mt-2 block text-sm text-mute">
                One workspace for your teachers, students and exams.
              </span>
            </Link>
            <Link
              to="/register"
              className="rounded-xl border border-line p-5 hover:border-pen"
            >
              <span className="block font-semibold text-pen">Parent</span>
              <span className="mt-2 block text-sm text-mute">
                A private space for your child’s learning.
              </span>
            </Link>
          </div>
          <p className="mt-7 border-t border-line pt-5 text-sm leading-relaxed text-mute">
            Upload your papers. Review AI-assisted evaluations. Understand where
            students can improve.
          </p>
        </div>
      </section>
    </main>
  );
}
