import { Suspense } from "react";
import type { Metadata } from "next";

import { PartiesView } from "./parties-view";

export const metadata: Metadata = {
  title: "Контрагенты — НПК Производство",
};

export default function PartiesPage() {
  return (
    <Suspense>
      <PartiesView />
    </Suspense>
  );
}
