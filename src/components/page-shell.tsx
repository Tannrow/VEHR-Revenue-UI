import type { ReactNode } from "react";

type PageShellProps = {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
};

export function PageShell({ title, description, children, footer }: PageShellProps) {
  return (
    <main className="min-h-screen bg-black px-6 py-12 text-white md:px-12">
      <div className="mx-auto max-w-6xl space-y-8">
        <header className="space-y-2">
          <h1 className="text-3xl font-bold md:text-4xl">{title}</h1>
          {description ? <p className="max-w-3xl text-zinc-400">{description}</p> : null}
        </header>

        {children}

        {footer ? (
          <footer className="border-t border-zinc-800 pt-6 text-sm text-zinc-500">{footer}</footer>
        ) : null}
      </div>
    </main>
  );
}

type SectionCardProps = {
  title: string;
  children: ReactNode;
};

export function SectionCard({ title, children }: SectionCardProps) {
  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900 p-6">
      <h2 className="mb-3 text-xl font-semibold">{title}</h2>
      {children}
    </section>
  );
}
