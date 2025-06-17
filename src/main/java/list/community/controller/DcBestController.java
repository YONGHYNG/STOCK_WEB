package list.community.controller;

import list.community.dto.DcPost;
import list.community.service.DcBestService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequestMapping("/api/community")
public class DcBestController {

    DcBestService dcBestService = new DcBestService();

    @GetMapping("/dcbest")
    public List<DcPost> getTopDcBestPosts() {
        return dcBestService.getTop10Posts();
    }

}
