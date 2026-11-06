import { Suspense } from "react";
import type { Metadata } from "next";

import { CutoffsView } from "./cutoffs-view";

export const metadata: Metadata = {
  title: "Отсечки — НПК Производство",
};

export default function CutoffsPage() {
  return (
    <Suspense>
      <CutoffsView />
    </Suspense>
  );
}
