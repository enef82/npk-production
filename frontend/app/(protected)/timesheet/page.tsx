import { Suspense } from "react";
import type { Metadata } from "next";

import { TimesheetView } from "./timesheet-view";

export const metadata: Metadata = {
  title: "Табель — НПК Производство",
};

export default function TimesheetPage() {
  return (
    <Suspense>
      <TimesheetView />
    </Suspense>
  );
}
