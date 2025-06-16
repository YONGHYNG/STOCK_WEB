package list.headline;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IndexController {

    private final IndexService indexService;

    @Autowired
    public IndexController(IndexService indexService) {
        this.indexService = indexService;
    }

    @GetMapping("/index")
    public String getIndexData() {
        try {
            return indexService.getIndexHtml();
        } catch (Exception e) {
            return "지수 정보를 가져오는 중 오류 발생: " + e.getMessage();
        }
    }
}
