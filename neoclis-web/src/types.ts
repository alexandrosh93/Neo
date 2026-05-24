export type VisitResponse = 'Yes' | 'No' | 'No Answer';

export interface Visit {
  id: string;
  visited_at: string;
  response: VisitResponse;
  created_at: string;
}
