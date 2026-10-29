; ISIR.ACL2.acl2_semantics
;
; Representation (list-based, matching isir_to_acl2.py):
;   - a value is an integer; `nil` denotes "undefined" (None).
;   - state / inputs / memories are lists, indexed by (nth id ...);
;     an uninitialized register reads as nil.
;   - an expression is an S-expression: an integer literal, or
;       (var i)       input
;       (read r)      register
;       (mem-read m a)
;       (not e)
;       (ite c t f)
;       (slice e high low)
;       (partial n)   partial_spec: non-deterministic width-n value
;       (add a b) (sub a b) (and a b) (or a b) (xor a b)
;       (eq a b) (neq a b) (lt a b) (le a b) (gt a b) (ge a b)
;       (shl a b) (shr a b)
;   - a rule is (cond action...) where cond is an expression and each
;     action is (write r e) or (mem-write m a d).
;   - a schedule is :parallel, :sequential, or :conflict-free.

(in-package "ACL2")

(include-book "arithmetic-5/top" :dir :system)

;; ------------------------------------------------------------------
;; 1. Width wrapping + bitwise operators
;; ------------------------------------------------------------------

(defun wrap (w v)
  (mod v (expt 2 w)))

(defun nat-and (a b) (logand a b))
(defun nat-or  (a b) (logior a b))
(defun nat-xor (a b) (logxor a b))

(defun bool-to-nat (b)
  (if b 1 0))

;; ------------------------------------------------------------------
;; 2. Binary operator evaluation (wrapped where the reference wraps)
;; ------------------------------------------------------------------

(defun binop-eval (op a b w)
  (case op
    (add (wrap w (+ a b)))
    (sub (wrap w (- (+ (expt 2 w) a) b)))   ; two's complement
    (and (nat-and a b))
    (or  (nat-or a b))
    (xor (nat-xor a b))
    (eq  (bool-to-nat (= a b)))
    (neq (bool-to-nat (not (= a b))))
    (lt  (bool-to-nat (< a b)))
    (le  (bool-to-nat (<= a b)))
    (gt  (bool-to-nat (> a b)))
    (ge  (bool-to-nat (>= a b)))
    (shl (wrap w (* a (expt 2 b))))
    (shr (wrap w (floor a (expt 2 b))))
    (otherwise nil)))

;; ------------------------------------------------------------------
;; 3. Expression evaluation
;; ------------------------------------------------------------------

(defun isir-eval (e w st inp mem)
  (declare (xargs :measure (acl2-count e)))
  (cond
   ((integerp e) e)                          ; literal
   ((atom e) nil)                            ; malformed
   ((eq (car e) 'var) (nth (cadr e) inp))
   ((eq (car e) 'read) (nth (cadr e) st))
   ((eq (car e) 'not)
    (let ((v (isir-eval (cadr e) w st inp mem)))
      (if (null v) nil (if (= v 0) 1 0))))
   ((eq (car e) 'ite)
    (let ((c (isir-eval (cadr e) w st inp mem)))
      (cond ((null c) nil)
            ((= c 0) (isir-eval (cadddr e) w st inp mem))
            (t (isir-eval (caddr e) w st inp mem)))))
   ((eq (car e) 'slice)
    (let ((v (isir-eval (cadr e) w st inp mem))
          (high (caddr e))
          (low (cadddr e)))
      (if (null v) nil
          (mod (floor v (expt 2 low)) (expt 2 (+ 1 (- high low)))))))
   ((eq (car e) 'partial) nil)               ; non-deterministic (see eval-nd)
   ((eq (car e) 'mem-read)
    (let ((a (isir-eval (caddr e) w st inp mem))
          (m (nth (cadr e) mem)))
      (if (or (null a) (null m)) nil (nth a m))))
   (t (let ((a (isir-eval (cadr e) w st inp mem))
            (b (isir-eval (caddr e) w st inp mem)))
        (if (or (null a) (null b)) nil
            (binop-eval (car e) a b w))))))

;; ------------------------------------------------------------------
;; 4. Rules, firing, and scheduling
;; ------------------------------------------------------------------

;; rule = (cond action ...)  -- cond is the rule's condition expression.
(defun rule-cond (r) (car r))
(defun rule-actions (r) (cdr r))

(defun fire (r st inp mem)
  (isir-eval (rule-cond r) 1 st inp mem))

;; Sequential grants: the first enabled rule wins; later rules are suppressed.
(defun grants-seq (fired)
  (if (endp fired)
      nil
    (if (car fired)
        (cons t (make-list (len (cdr fired)) :initial-element nil))
      (cons nil (grants-seq (cdr fired))))))

(defun grants (sched fired)
  (if (eq sched :sequential) (grants-seq fired) fired))

;; ------------------------------------------------------------------
;; 5. Action application + the single-cycle step
;; ------------------------------------------------------------------

;; width maps are lists: (nth id rw) is the register width.
(defun apply-action (rw mem-w act st inp mem)
  (if (eq (car act) 'write)
      (let* ((dest (cadr act))
             (w (nth dest rw))
             (v (isir-eval (caddr act) w st inp mem)))
        (if (null v)
            nil
          (cons (update-nth dest (wrap w v) st) mem)))
    ;; mem-write
    (let* ((mid (cadr act))
           (addr (isir-eval (caddr act) 1 st inp mem))
           (data (isir-eval (cadddr act) (nth mid mem-w) st inp mem))
           (m (nth mid mem)))
      (if (or (null addr) (null data))
          nil
        (cons st (update-nth mid (update-nth addr data m) mem))))))

(defun apply-actions (rw mem-w acts st inp mem)
  (if (endp acts)
      (cons st mem)
    (let ((p (apply-action rw mem-w (car acts) st inp mem)))
      (if (null p)
          nil
        (apply-actions rw mem-w (cdr acts) (car p) inp (cdr p))))))

(defun granted-actions (rules gs)
  (if (endp rules)
      nil
    (if (car gs)
        (append (rule-actions (car rules))
                (granted-actions (cdr rules) (cdr gs)))
      (granted-actions (cdr rules) (cdr gs)))))

(defun map-fire (rules st inp mem)
  (if (endp rules)
      nil
    (cons (fire (car rules) st inp mem) (map-fire (cdr rules) st inp mem))))

(defun all-defined (fired)
  (if (endp fired)
      t
    (and (not (null (car fired))) (all-defined (cdr fired)))))

(defun map-fireb (fired)
  (if (endp fired)
      nil
    (cons (if (and (not (null (car fired))) (not (= (car fired) 0))) t nil)
          (map-fireb (cdr fired)))))

(defun isir-step (sched rules rw mem-w st inp mem)
  (let ((fired (map-fire rules st inp mem)))
    (if (not (all-defined fired))
        nil
      (let ((gs (grants sched (map-fireb fired))))
        (apply-actions rw mem-w (granted-actions rules gs) st inp mem)))))

;; ------------------------------------------------------------------
;; 6. n-step reachability (clocked) + the observable projection
;; ------------------------------------------------------------------

(defun isir-stepn (n sched rules rw mem-w st inp mem)
  (if (zp n)
      st
    (let ((p (isir-step sched rules rw mem-w st inp mem)))
      (if (null p)
          nil
        (isir-stepn (1- n) sched rules rw mem-w (car p) inp (cdr p))))))

;; Identity observable projection (first cut; mirrors isir.v's obs).
(defun obs (st) st)

;; ------------------------------------------------------------------
;; 7. partial_spec: explicit non-determinism (unconstrained placeholder)
;; ------------------------------------------------------------------

(encapsulate
  (((partial-value * *) => *))
  (local (defun partial-value (n st) (declare (ignore n st)) 0))
  (defthm partial-value-bounded
    (implies (natp n) (< (partial-value n st) (expt 2 n)))))

;; A partial_spec placeholder may produce any value of its width.
(defun isir-eval-nd (e w st inp mem v)
  (cond
   ((and (consp e) (eq (car e) 'partial))
    (< v (expt 2 (cadr e))))
   (t (equal v (isir-eval e w st inp mem)))))

;; ------------------------------------------------------------------
;; 8. Worked example: ALU result = a + b (wrapped to 8 bits)
;; ------------------------------------------------------------------

;; (write 0 (add (var 0) (var 1))) with condition true (= literal 1).
(defun alu-add-rule ()
  (list 1 (list 'write 0 (list 'add (list 'var 0) (list 'var 1)))))

(defun alu-rw () (list 8))     ; register 0 has width 8
(defun alu-mem-w () (list 1))  ; no memories used

;; a=250, b=10: 250+10 = 260 = 4 (mod 256), matching the fixed-width semantics.
(defthm alu-add-wraps
  (equal (isir-step :parallel (list (alu-add-rule)) (alu-rw) (alu-mem-w)
               nil (list 250 10) nil)
         (cons (list 4) nil))
  :hints (("Goal" :in-theory (enable isir-step apply-actions apply-action
                                      granted-actions grants map-fireb map-fire
                                      all-defined fire rule-cond rule-actions
                                      isir-eval binop-eval wrap nat-and nat-or
                                      nat-xor bool-to-nat))))

;; The observable projection of the stepped state retains the result.
(defthm alu-add-obs
  (equal (obs (car (isir-step :parallel (list (alu-add-rule)) (alu-rw) (alu-mem-w)
                         nil (list 250 10) nil)))
         (list 4))
  :hints (("Goal" :in-theory (enable obs isir-step apply-actions apply-action
                                      granted-actions grants map-fireb map-fire
                                      all-defined fire rule-cond rule-actions
                                      isir-eval binop-eval wrap nat-and nat-or
                                      nat-xor bool-to-nat))))

