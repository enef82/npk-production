import type { Metadata } from "next";

import { WorkCentersView } from "@/components/production/work-centers-view";

export const metadata: Metadata = {
  title: "Участки — НПК Производство",
};

export default function WorkCentersPage() {
  return <WorkCentersView />;
}
