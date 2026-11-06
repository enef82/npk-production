import { Suspense } from "react";
import type { Metadata } from "next";

import { EnergyView } from "./energy-view";

export const metadata: Metadata = {
  title: "Энергоучёт — НПК Производство",
};

export default function EnergyPage() {
  return (
    <Suspense>
      <EnergyView />
    </Suspense>
  );
}
