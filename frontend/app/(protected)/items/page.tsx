import { Suspense } from "react";
import type { Metadata } from "next";

import { ItemsView } from "./items-view";

export const metadata: Metadata = {
  title: "Номенклатура — НПК Производство",
};

export default function ItemsPage() {
  return (
    <Suspense>
      <ItemsView />
    </Suspense>
  );
}
