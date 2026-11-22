/*
 * CPU Scheduling Algorithms
 *   1. FCFS         (non-preemptive)
 *   2. SJF          (non-preemptive, shortest burst first)
 *   3. Priority     (non-preemptive, LOWER number = HIGHER priority)
 *   4. Round Robin  (preemptive, user-defined time quantum)
 *
 * Compile : gcc cpu_scheduling.c -o cpu_scheduling
 * Run     : ./cpu_scheduling
 */

#include <stdio.h>
#include <string.h>

#define MAX 50

typedef struct {
    int pid;        /* process id            */
    int at;         /* arrival time          */
    int bt;         /* burst time            */
    int pr;         /* priority              */
    int rem;        /* remaining burst time  */
    int ct;         /* completion time       */
    int tat;        /* turnaround time       */
    int wt;         /* waiting time          */
    int done;       /* finished flag         */
} Process;

/* ---------- Gantt chart storage ---------- */
int seg_pid[1000], seg_s[1000], seg_e[1000], nseg;

void gantt_reset(void) { nseg = 0; }

void gantt_add(int pid, int s, int e) {
    if (nseg > 0 && seg_pid[nseg - 1] == pid && seg_e[nseg - 1] == s) {
        seg_e[nseg - 1] = e;            /* merge consecutive slices */
        return;
    }
    seg_pid[nseg] = pid; seg_s[nseg] = s; seg_e[nseg] = e;
    nseg++;
}

void gantt_print(void) {
    int i;
    printf("\nGantt Chart:\n ");
    for (i = 0; i < nseg; i++) printf("--------");
    printf("\n|");
    for (i = 0; i < nseg; i++) {
        if (seg_pid[i] == 0) printf(" Idle  |");
        else                 printf("  P%-3d |", seg_pid[i]);
    }
    printf("\n ");
    for (i = 0; i < nseg; i++) printf("--------");
    printf("\n");
    for (i = 0; i < nseg; i++) printf("%-8d", seg_s[i]);
    printf("%d\n", seg_e[nseg - 1]);
}

/* ---------- Result table ---------- */
void print_results(Process p[], int n, int show_pr) {
    int i;
    float tw = 0, tt = 0;

    printf("\n");
    if (show_pr) printf("PID\tAT\tBT\tPR\tCT\tTAT\tWT\n");
    else         printf("PID\tAT\tBT\tCT\tTAT\tWT\n");

    for (i = 0; i < n; i++) {
        p[i].tat = p[i].ct - p[i].at;
        p[i].wt  = p[i].tat - p[i].bt;
        tw += p[i].wt;
        tt += p[i].tat;
        if (show_pr)
            printf("P%d\t%d\t%d\t%d\t%d\t%d\t%d\n", p[i].pid, p[i].at, p[i].bt,
                   p[i].pr, p[i].ct, p[i].tat, p[i].wt);
        else
            printf("P%d\t%d\t%d\t%d\t%d\t%d\n", p[i].pid, p[i].at, p[i].bt,
                   p[i].ct, p[i].tat, p[i].wt);
    }
    gantt_print();
    printf("\nAverage Waiting Time    : %.2f", tw / n);
    printf("\nAverage Turnaround Time : %.2f\n", tt / n);
}

/* ---------- Reset a working copy ---------- */
void reset(Process dst[], Process src[], int n) {
    int i;
    for (i = 0; i < n; i++) {
        dst[i] = src[i];
        dst[i].rem = dst[i].bt;
        dst[i].done = 0;
        dst[i].ct = dst[i].tat = dst[i].wt = 0;
    }
    gantt_reset();
}

/* ---------- Index order sorted by arrival (stable) ---------- */
void sort_by_arrival(Process p[], int n, int ord[]) {
    int i, j, t;
    for (i = 0; i < n; i++) ord[i] = i;
    for (i = 0; i < n - 1; i++)
        for (j = 0; j < n - i - 1; j++)
            if (p[ord[j]].at > p[ord[j + 1]].at) {
                t = ord[j]; ord[j] = ord[j + 1]; ord[j + 1] = t;
            }
}

/* ================= 1. FCFS ================= */
void fcfs(Process src[], int n) {
    Process p[MAX];
    int ord[MAX], i, time = 0;

    reset(p, src, n);
    sort_by_arrival(p, n, ord);

    for (i = 0; i < n; i++) {
        Process *x = &p[ord[i]];
        if (time < x->at) {
            gantt_add(0, time, x->at);   /* CPU idle */
            time = x->at;
        }
        gantt_add(x->pid, time, time + x->bt);
        time += x->bt;
        x->ct = time;
    }
    printf("\n===== FCFS Scheduling =====");
    print_results(p, n, 0);
}

/* ===== Shared engine: non-preemptive SJF / Priority =====
 * mode 0 -> pick smallest burst time
 * mode 1 -> pick smallest priority number
 * Ties are broken by earlier arrival, then lower index.
 */
void non_preemptive(Process src[], int n, int mode) {
    Process p[MAX];
    int time = 0, completed = 0, i, best, next_at;

    reset(p, src, n);

    while (completed < n) {
        best = -1;
        for (i = 0; i < n; i++) {
            if (p[i].done || p[i].at > time) continue;
            if (best == -1) { best = i; continue; }
            int a = mode ? p[i].pr : p[i].bt;
            int b = mode ? p[best].pr : p[best].bt;
            if (a < b || (a == b && p[i].at < p[best].at)) best = i;
        }

        if (best == -1) {                /* nobody has arrived yet -> idle */
            next_at = -1;
            for (i = 0; i < n; i++)
                if (!p[i].done && (next_at == -1 || p[i].at < next_at))
                    next_at = p[i].at;
            gantt_add(0, time, next_at);
            time = next_at;
            continue;
        }

        gantt_add(p[best].pid, time, time + p[best].bt);
        time += p[best].bt;
        p[best].ct = time;
        p[best].done = 1;
        completed++;
    }

    printf(mode ? "\n===== Priority Scheduling (Non-Preemptive) ====="
                : "\n===== SJF Scheduling (Non-Preemptive) =====");
    print_results(p, n, mode);
}

/* ================= 4. Round Robin ================= */
void round_robin(Process src[], int n, int tq) {
    Process p[MAX];
    int ord[MAX], q[MAX + 1], f = 0, r = 0, cnt = 0;
    int time = 0, done = 0, next = 0, i, run;

    reset(p, src, n);
    sort_by_arrival(p, n, ord);

    while (done < n) {
        /* admit everything that has arrived */
        while (next < n && p[ord[next]].at <= time) {
            q[r] = ord[next++]; r = (r + 1) % (MAX + 1); cnt++;
        }

        if (cnt == 0) {                  /* idle until next arrival */
            gantt_add(0, time, p[ord[next]].at);
            time = p[ord[next]].at;
            continue;
        }

        i = q[f]; f = (f + 1) % (MAX + 1); cnt--;

        run = (p[i].rem < tq) ? p[i].rem : tq;
        gantt_add(p[i].pid, time, time + run);
        time += run;
        p[i].rem -= run;

        /* new arrivals go in BEFORE the preempted process */
        while (next < n && p[ord[next]].at <= time) {
            q[r] = ord[next++]; r = (r + 1) % (MAX + 1); cnt++;
        }

        if (p[i].rem > 0) {
            q[r] = i; r = (r + 1) % (MAX + 1); cnt++;
        } else {
            p[i].ct = time;
            done++;
        }
    }

    printf("\n===== Round Robin Scheduling (TQ = %d) =====", tq);
    print_results(p, n, 0);
}

/* ================= main ================= */
int main(void) {
    Process p[MAX];
    int n, i, choice, tq;

    printf("Enter number of processes (max %d): ", MAX);
    if (scanf("%d", &n) != 1 || n < 1 || n > MAX) {
        printf("Invalid number of processes.\n");
        return 1;
    }

    for (i = 0; i < n; i++) {
        p[i].pid = i + 1;
        printf("P%d -> Arrival Time, Burst Time, Priority: ", i + 1);
        if (scanf("%d %d %d", &p[i].at, &p[i].bt, &p[i].pr) != 3 || p[i].bt <= 0) {
            printf("Invalid input.\n");
            return 1;
        }
    }

    do {
        printf("\n========== CPU SCHEDULER ==========\n");
        printf("1. FCFS\n");
        printf("2. SJF (Non-Preemptive)\n");
        printf("3. Priority (Non-Preemptive, lower no. = higher priority)\n");
        printf("4. Round Robin\n");
        printf("5. Run ALL\n");
        printf("0. Exit\n");
        printf("Choice: ");
        if (scanf("%d", &choice) != 1) break;

        switch (choice) {
            case 1: fcfs(p, n); break;
            case 2: non_preemptive(p, n, 0); break;
            case 3: non_preemptive(p, n, 1); break;
            case 4:
                printf("Enter time quantum: ");
                if (scanf("%d", &tq) == 1 && tq > 0) round_robin(p, n, tq);
                else printf("Invalid time quantum.\n");
                break;
            case 5:
                printf("Enter time quantum for Round Robin: ");
                if (scanf("%d", &tq) != 1 || tq <= 0) { printf("Invalid time quantum.\n"); break; }
                fcfs(p, n);
                non_preemptive(p, n, 0);
                non_preemptive(p, n, 1);
                round_robin(p, n, tq);
                break;
            case 0: printf("Bye!\n"); break;
            default: printf("Invalid choice.\n");
        }
    } while (choice != 0);

    return 0;
}
