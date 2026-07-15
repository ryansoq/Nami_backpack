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
  %addtmp = add i32 %a1, %b2
  %addtmp3 = add i32 %addtmp, 2
  %c = alloca i32, align 4
  store i32 %addtmp3, ptr %c, align 4
  %a4 = load i32, ptr %a, align 4
  %b5 = load i32, ptr %b, align 4
  %addtmp6 = add i32 %a4, %b5
  %c7 = load i32, ptr %c, align 4
  %addtmp8 = add i32 %addtmp6, %c7
  %d = alloca i32, align 4
  store i32 %addtmp8, ptr %d, align 4
  %d9 = load i32, ptr %d, align 4
  ret i32 %d9
}
