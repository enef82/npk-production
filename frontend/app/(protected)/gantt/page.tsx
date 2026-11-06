import type { Metadata } from "next";

import { CardHost } from "@/components/production/card-host";
import { GanttView } from "@/components/production/gantt-view";

export const metadata: Metadata = {
  title: "План-график — НПК Производство",
};

export default function GanttPage() {
  return (
    <CardHost>
      <GanttView />
    </CardHost>
  );
}
