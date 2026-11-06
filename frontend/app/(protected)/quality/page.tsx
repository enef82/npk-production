import { Suspense } from "react";
import type { Metadata } from "next";

import { QualityView } from "./quality-view";

export const metadata: Metadata = {
  title: "Качество — НПК Производство",
};

export default function QualityPage() {
  return (
    <Suspense>
      <QualityView />
    </Suspense>
  );
}
