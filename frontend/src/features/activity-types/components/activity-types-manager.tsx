"use client";

import * as React from "react";
import { PencilLine, PlusCircle, PowerOff } from "lucide-react";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { AppError } from "@/lib/api-client";

import {
  useActivityTypes,
  useCreateActivityType,
  useUpdateActivityType,
  useDeactivateActivityType,
} from "../hooks";
import type { ActivityType } from "../types";

const CATEGORIES = ["GENERAL", "PROJECT", "TAG_ESTIMATION"] as const;
const CATEGORY_LABEL: Record<string, string> = {
  GENERAL: "General",
  PROJECT: "Project J-Code",
  TAG_ESTIMATION: "Tag Estimation",
};

const formSchema = z.object({
  code: z.string().trim().min(1, "Code is required").max(10),
  name: z.string().trim().min(1, "Name is required").max(200),
  category: z.enum(CATEGORIES),
  requires_project: z.boolean(),
});
type FormValues = z.infer<typeof formSchema>;

const EMPTY: FormValues = {
  code: "",
  name: "",
  category: "GENERAL",
  requires_project: false,
};

function ActivityTypeForm({
  editing,
  onDone,
}: {
  editing: ActivityType | null;
  onDone: () => void;
}) {
  const createMutation = useCreateActivityType();
  const updateMutation = useUpdateActivityType(editing?.id ?? "");

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: editing
      ? {
          code: editing.code ?? "",
          name: editing.name,
          category: editing.category as (typeof CATEGORIES)[number],
          requires_project: editing.requires_project,
        }
      : EMPTY,
  });

  const category = form.watch("category");
  React.useEffect(() => {
    if (category === "PROJECT") form.setValue("requires_project", true);
    else form.setValue("requires_project", false);
  }, [category, form]);

  async function onSubmit(values: FormValues) {
    try {
      if (editing) {
        await updateMutation.mutateAsync({
          name: values.name,
          category: values.category,
          requires_project: values.requires_project,
        });
        toast.success("Activity type updated");
      } else {
        await createMutation.mutateAsync(values);
        toast.success("Activity type created");
        form.reset(EMPTY);
      }
      onDone();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Something went wrong.");
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {editing
            ? `Edit: ${editing.code ? `${editing.code} — ` : ""}${editing.name}`
            : "New Activity Type"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3" noValidate>
            <div className="grid gap-3 sm:grid-cols-4">
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Code</FormLabel>
                    <FormControl>
                      <Input {...field} disabled={!!editing} placeholder="e.g. 10" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Activity Name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="e.g. ADMIN SUPPORT" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="category"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Category</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {CATEGORIES.map((c) => (
                          <SelectItem key={c} value={c}>
                            {CATEGORY_LABEL[c]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" loading={isPending} size="sm">
                {editing ? "Save changes" : "Create"}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={onDone}>
                Cancel
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

export function ActivityTypesManager() {
  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState<ActivityType | null>(null);
  const [search, setSearch] = React.useState("");

  const query = useActivityTypes({ active_only: false, limit: 200 });
  const deactivateMutation = useDeactivateActivityType();

  const items = query.data?.items ?? [];
  const filtered = items.filter(
    (a) =>
      (a.code ?? "").toLowerCase().includes(search.toLowerCase()) ||
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.category.toLowerCase().includes(search.toLowerCase()),
  );

  function startEdit(at: ActivityType) {
    setEditing(at);
    setShowForm(true);
  }

  function closeForm() {
    setEditing(null);
    setShowForm(false);
  }

  async function handleDeactivate(at: ActivityType) {
    try {
      await deactivateMutation.mutateAsync(at.id);
      toast.success(`"${at.name}" deactivated`);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not deactivate.");
    }
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3">
        <Input
          placeholder="Search by code, name, or category…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        {!showForm && (
          <Button size="sm" onClick={() => { setEditing(null); setShowForm(true); }}>
            <PlusCircle className="h-4 w-4" />
            New Activity Type
          </Button>
        )}
      </div>

      {/* Form */}
      {showForm && <ActivityTypeForm editing={editing} onDone={closeForm} />}

      {/* Table */}
      <Card className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-20">Code</TableHead>
              <TableHead>Activity Name</TableHead>
              <TableHead>Category</TableHead>
              <TableHead className="w-28 text-center">Req. Project</TableHead>
              <TableHead className="w-24 text-center">Status</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.isLoading && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!query.isLoading && filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  No activity types found.
                </TableCell>
              </TableRow>
            )}
            {filtered.map((at) => (
              <TableRow key={at.id} className={!at.is_active ? "opacity-50" : ""}>
                <TableCell className="font-mono text-sm">{at.code ?? "—"}</TableCell>
                <TableCell className="font-medium">{at.name}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-xs">
                    {CATEGORY_LABEL[at.category] ?? at.category}
                  </Badge>
                </TableCell>
                <TableCell className="text-center text-sm text-muted-foreground">
                  {at.requires_project ? "Yes" : "No"}
                </TableCell>
                <TableCell className="text-center">
                  <Badge variant={at.is_active ? "success" : "neutral"} dot>
                    {at.is_active ? "Active" : "Inactive"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => startEdit(at)}
                      aria-label="Edit"
                    >
                      <PencilLine className="h-3.5 w-3.5" />
                    </Button>
                    {at.is_active && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={() => void handleDeactivate(at)}
                        aria-label="Deactivate"
                        disabled={deactivateMutation.isPending}
                      >
                        <PowerOff className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
