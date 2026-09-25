/**
 * Файловый выбор с собственным лейблом: системная кнопка браузера
 * не поддаётся стилизации и выбивается из интерфейса.
 * Можно перетащить файл на поле.
 */
export default function FileField({
  value,
  placeholder = "Файл не выбран",
  buttonText = "Выбрать файл",
  disabled = false,
  onChange,
  ...inputProps
}) {
  const className = [
    "filefield",
    value ? "has-file" : "",
    disabled ? "is-disabled" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const emit = (fileList) => {
    if (!fileList?.length || disabled) return;
    onChange?.({ target: { files: fileList } });
  };

  return (
    <label
      className={className}
      onDragOver={(e) => {
        e.preventDefault();
        e.stopPropagation();
      }}
      onDrop={(e) => {
        e.preventDefault();
        e.stopPropagation();
        emit(e.dataTransfer.files);
      }}
    >
      <input
        type="file"
        disabled={disabled}
        {...inputProps}
        onChange={(e) => emit(e.target.files)}
      />
      <span className="filefield-btn">{buttonText}</span>
      <span className="filefield-text">{value || placeholder}</span>
    </label>
  );
}
