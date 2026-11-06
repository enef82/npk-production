import { Suspense } from "react";
import type { Metadata } from "next";

import { SupplyView } from "./supply-view";

export const metadata: Metadata = {
  title: "Закупки и склад — НПК Производство",
};

export default function SupplyPage() {
  return (
    <Suspense>
      <SupplyView />
    </Suspense>
  );
}
