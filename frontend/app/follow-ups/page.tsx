"use client";

import { Guard } from "@/components/Session";
import FollowUpQueue from "@/components/follow-ups/FollowUpQueue";

export default function FollowUpsPage() {
  return <Guard permission="leads.view"><FollowUpQueue /></Guard>;
}