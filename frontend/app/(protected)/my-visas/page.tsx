import type { Metadata } from "next";

import { CardHost } from "@/components/production/card-host";
import { MyVisasView } from "@/components/production/my-visas-view";

export const metadata: Metadata = {
  title: "Мои визы — НПК Производство",
};

export default function MyVisasPage() {
  return (
    <CardHost>
      <MyVisasView />
    </CardHost>
  );
}
