; ModuleID = 'mini'
source_filename = "mini"

define i32 @main() {
entry:
  %a = alloca i32, align 4
  store i32 5, ptr %a, align 4
  %b = alloca i32, align 4
  store i32 7, ptr %b, align 4
  %a1 = load i32, ptr %a, align 4
  %b2 = load i32, ptr %b, align 4
  %c = add i32 %a1, %b2
  %c3 = alloca i32, align 4
  store i32 %c, ptr %c3, align 4
  %c4 = load i32, ptr %c3, align 4
  ret i32 %c4
}
