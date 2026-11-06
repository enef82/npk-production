import type { Metadata } from "next";

import { BoardView } from "@/components/production/board-view";
import { CardHost } from "@/components/production/card-host";

export const metadata: Metadata = {
  title: "Заявка — НПК Производство",
};

// Карточка заявки по прямой ссылке — боковая панель поверх доски, как при открытии с неё.
export default async function InquiryPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <CardHost basePath="/board" initial={{ kind: "inquiry", id }}>
      <BoardView />
    </CardHost>
  );
}
