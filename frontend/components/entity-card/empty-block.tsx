export function EntityCardEmptyBlock({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{title}</p>
      <p>{description}</p>
    </div>
  );
}
