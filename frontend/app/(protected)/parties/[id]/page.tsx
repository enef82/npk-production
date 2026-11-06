import { PartyCardView } from "./party-card-view";

export default async function PartyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PartyCardView partyId={id} />;
}
