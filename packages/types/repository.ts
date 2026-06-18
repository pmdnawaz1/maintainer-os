export interface Repository {
  id: number;
  full_name: string;
  owner: string;
  name: string;
  installation_id: number | null;
  created_at: string;
}
