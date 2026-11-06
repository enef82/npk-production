import type { Metadata } from "next";

import { CardHost } from "@/components/production/card-host";

import { PortfolioView } from "./portfolio-view";

export const metadata: Metadata = {
  title: "Портфель — НПК Производство",
};

export default function PortfolioPage() {
  return (
    <CardHost>
      <PortfolioView />
    </CardHost>
  );
}
