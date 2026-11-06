import type { Metadata } from "next";

import { LoadView } from "./load-view";

export const metadata: Metadata = {
  title: "Загрузка участков — НПК Производство",
};

export default function LoadPage() {
  return <LoadView />;
}
