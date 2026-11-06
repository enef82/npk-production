import type { Metadata } from "next";

import { CardHost } from "@/components/production/card-host";

import { EmployeesView } from "./employees-view";

export const metadata: Metadata = {
  title: "Сотрудники — НПК Производство",
};

export default function EmployeesPage() {
  return (
    <CardHost>
      <EmployeesView />
    </CardHost>
  );
}
