import type { Metadata } from "next";

import { BoardView } from "@/components/production/board-view";
import { CardHost } from "@/components/production/card-host";

export const metadata: Metadata = {
  title: "Доска — НПК Производство",
};

export default function BoardPage() {
  return (
    <CardHost basePath="/board">
      <BoardView />
    </CardHost>
  );
}
