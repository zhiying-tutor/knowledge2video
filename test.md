```ps
@'
{"knowledge_point":"二分搜索","age":20,"gender":"男","language":"Python","duration":5,"difficulty":"medium","extra_info":"我是大学生，有一定编程基础，想深入理解算法"}
'@ > body.json
```

```ps
curl.exe -v -N -X POST "http://127.0.0.1:8080/api/v1/generate-video" `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-api-key-12345" `
  --data-binary "@body.json"
```