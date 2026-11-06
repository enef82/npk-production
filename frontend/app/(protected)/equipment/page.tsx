import { Suspense } from "react";
import type { Metadata } from "next";

import { EquipmentView } from "./equipment-view";

export const metadata: Metadata = {
  title: "Оборудование — НПК Производство",
};

export default function EquipmentPage() {
  return (
    <Suspense>
      <EquipmentView />
    </Suspense>
  );
}
