export default function Home() {
  return (
    <main className="mx-auto grid max-w-2xl gap-2 px-6 py-16">
      <h1 className="text-xl font-semibold">Cierre de octubre 2026</h1>
      <p className="text-ink-muted">
        La consola del contador está en construcción. La API corre en{" "}
        <a className="text-primary underline" href={`${process.env.NEXT_PUBLIC_API_URL}/docs`}>
          /docs
        </a>
        .
      </p>
    </main>
  );
}
